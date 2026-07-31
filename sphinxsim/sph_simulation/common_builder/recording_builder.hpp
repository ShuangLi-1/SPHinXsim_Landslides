#ifndef RECORDING_BUILDER_HPP
#define RECORDING_BUILDER_HPP

#include "recording_builder.h"

#include "sph_simulation.h"

namespace SPH
{
// SPHinXsim runs all internal dynamics in ScalingConfig's nondimensional
// units (e.g. Mass is scaled by the "Density"/"Mass" characteristic
// dimension, see base_simulation_builder.cpp jsonToReal(..., "Density")).
// The shared ReducedQuantityRecording writes whatever unit the reduce method
// produces, which is correct for plain (unscaled) SPHinXsys use, such as the
// SYCL reference, but wrong here unless converted back to physical units at
// write time - the same conversion createBodyStatesRecording and the
// observer recorder already apply via DiscreteVariable::setScalingRef.
template <class ExecutionPolicy, class LocalReduceMethodType>
class ScaledReducedQuantityRecording : public ReducedQuantityRecording<ExecutionPolicy, LocalReduceMethodType>
{
    using Base = ReducedQuantityRecording<ExecutionPolicy, LocalReduceMethodType>;
    Real physical_scaling_ref_;

  public:
    template <class DynamicsIdentifier, typename... Args>
    ScaledReducedQuantityRecording(Real physical_scaling_ref, DynamicsIdentifier &identifier, Args &&...args)
        : Base(identifier, std::forward<Args>(args)...),
          physical_scaling_ref_(physical_scaling_ref) {}

    virtual void writeToFile(size_t iteration_step = 0) override
    {
        if (!this->header_written_)
        {
            std::ofstream out_file(this->filefullpath_output_.c_str(), std::ios::out);
            out_file << "\"run_time\""
                     << "   ";
            this->plt_engine_.writeAQuantityHeader(out_file, this->reduced_quantity_, this->quantity_name_);
            out_file << "\n";
            out_file.close();
            this->header_written_ = true;
        }
        std::ofstream out_file(this->filefullpath_output_.c_str(), std::ios::app);
        out_file << this->sv_physical_time_->getValue() << "   ";
        this->reduced_quantity_ = this->reduce_method_.exec() * physical_scaling_ref_;
        this->plt_engine_.writeAQuantity(out_file, this->reduced_quantity_);
        out_file << "\n";
        out_file.close();
    }
};
//=================================================================================================//
template <class MethodContainerType>
BodyStatesRecording &RecordingBuilder::createBodyStatesRecording(
    SPHSystem &sph_system, EntityManager &config_manager,
    MethodContainerType &main_methods, const json &config)
{
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    auto &state_recorder = main_methods.template addBodyStateRecorder<
        BodyStatesRecordingToVtpCK>(sph_system);

    if (config.contains("extra_state_recording"))
    {
        for (auto &body : config.at("extra_state_recording"))
        {
            std::string body_name = body.at("name").get<std::string>();
            auto &real_body = sph_system.getBodyByName<RealBody>(body_name);
            for (auto &var : body.at("variables"))
            {
                addVariableToStateRecorder(state_recorder, real_body, var);
            }
        }
    }

    for (auto &body : state_recorder.getBodiesForRecording())
    {
        auto &base_particles = body->getBaseParticles();
        base_particles.dvParticlePosition()->setScalingRef(scaling_config.getScalingRef("Length"));
        auto &variables_to_write = base_particles.VariablesToWrite();
        // For now, set scaling reference for variables to write, if any, according to their unit type.
        // Variables without registered scaling references will not be scaled,
        // as they are considered as temporary variables for debug purposes only.
        constexpr int type_index_Real = DataTypeIndex<Real>::value;
        for (DiscreteVariable<Real> *variable : std::get<type_index_Real>(variables_to_write))
        {
            variable->setScalingRef(scaling_config.getScalingRef(variable->Name(), false));
        }

        constexpr int type_index_Vecd = DataTypeIndex<Vecd>::value;
        for (DiscreteVariable<Vecd> *variable : std::get<type_index_Vecd>(variables_to_write))
        {
            variable->setScalingRef(scaling_config.getScalingRef(variable->Name(), false));
        }

        constexpr int type_index_Matd = DataTypeIndex<Matd>::value;
        for (DiscreteVariable<Matd> *variable : std::get<type_index_Matd>(variables_to_write))
        {
            variable->setScalingRef(scaling_config.getScalingRef(variable->Name(), false));
        }
    }
    return state_recorder;
}
//=================================================================================================//
template <class MethodContainerType>
void RecordingBuilder::buildObservationIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, const json &config)
{
    auto &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();

    if (config.contains("observers"))
    {
        addObserves(sph_system, config_manager, config.at("observers"));
        auto &observer_config_dynamics =
            createObserverConfigurationDynamics(sph_system, config_manager, main_methods);
        auto &observer_io = addObserveRecorder(sph_system, config_manager, main_methods);

        auto &time_stepper = sim.getSPHSolver().getTimeStepper();

        auto &initialization_pipeline = sim.getInitializationPipeline();
        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialObservation, [&]()
            {
                observer_config_dynamics.exec();
                observer_io.writeToFile(time_stepper.getIterationStep()); });

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::Observation, [&]()
            {
                    observer_config_dynamics.exec();
                    observer_io.writeToFile(time_stepper.getIterationStep()); });
    }
}
//=================================================================================================//
template <class MethodContainerType>
void RecordingBuilder::buildEnergyRecordingIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, const json &config)
{
    if (!config.contains("energy_recording"))
    {
        return;
    }

    auto &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    auto &time_stepper = sim.getSPHSolver().getTimeStepper();

    auto &energy_io = main_methods.addIODynamicsGroup(sph_system);
    bool has_entries = false;

    for (const auto &entry : config.at("energy_recording"))
    {
        std::string name = entry.at("name").get<std::string>();
        std::string body_name = entry.at("body").get<std::string>();
        std::string quantity = entry.value("quantity", std::string("TotalMechanicalEnergy"));
        RealBody &body = sph_system.getBodyByName<RealBody>(body_name);

        Vecd gravity_vector = Vecd::Zero();
        if (entry.contains("gravity"))
        {
            gravity_vector = scaling_config.jsonToVecd(entry.at("gravity"), "Acceleration");
        }
        Gravity *gravity = config_manager.emplaceEntity<Gravity>(name + "_Gravity", gravity_vector);

        if (quantity == "TotalMechanicalEnergy")
        {
            // Converts the reduced quantity (computed from internally-scaled
            // Mass/Velocity/Acceleration) back to physical Joules.
            Real energy_scaling_ref = scaling_config.getScalingRef("Energy");
            auto &recorder = main_methods.template addIODynamics<
                ScaledReducedQuantityRecording, TotalMechanicalEnergyCK>(
                energy_scaling_ref, body, *gravity);
            energy_io.add(&recorder);
            has_entries = true;
        }
        else
        {
            throw std::runtime_error(
                "RecordingBuilder::buildEnergyRecordingIfPresent: unsupported quantity: " + quantity);
        }
    }

    if (!has_entries)
    {
        return;
    }

    auto &initialization_pipeline = sim.getInitializationPipeline();
    initialization_pipeline.insert_hook(
        InitializationHookPoint::InitialObservation, [&]()
        { energy_io.writeToFile(time_stepper.getIterationStep()); });

    auto &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::Observation, [&]()
        { energy_io.writeToFile(time_stepper.getIterationStep()); });
}
//=================================================================================================//
template <class MethodContainerType>
ParticleDynamicsGroup &RecordingBuilder::createObserverConfigurationDynamics(
    SPHSystem &sph_system, EntityManager &config_manager, MethodContainerType &main_methods)
{
    auto &observer_config_dynamics = main_methods.addParticleDynamicsGroup();

    StdVec<ObserverConfig *> observer_configs = config_manager.entitiesWith<ObserverConfig>();
    if (!observer_configs.empty())
    {
        for (auto &observer_config : observer_configs)
        {
            ObserverBody &observer_body = sph_system.getBodyByName<ObserverBody>(observer_config->name_);
            RealBody &observed_body = sph_system.getBodyByName<RealBody>(observer_config->observed_body_);
            auto &observer_relation = sph_system.addContactRelation(observer_body, observed_body);
            observer_config_dynamics.add(&main_methods.addRelationDynamics(observer_relation));
        }
    }
    return observer_config_dynamics;
}
//=================================================================================================//
template <class MethodContainerType>
IODynamicsGroup &RecordingBuilder::addObserveRecorder(
    SPHSystem &sph_system, EntityManager &config_manager, MethodContainerType &main_methods)
{
    auto &observer_io = main_methods.addIODynamicsGroup(sph_system);

    StdVec<ObserverConfig *> observer_configs = config_manager.entitiesWith<ObserverConfig>();
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    if (!observer_configs.empty())
    {
        for (auto &observer_config : observer_configs)
        {
            std::string relation_name = getObserverRelationName(*observer_config);
            auto &observer_relation = sph_system.getRelationByName<
                Contact<Relation<ObserverBody, RealBody>>>(relation_name);

            observer_io.add(addObserveRecorderWithVariableConfig(
                scaling_config, observer_config->observed_variable_, main_methods, observer_relation));
        }
    }
    return observer_io;
}
//=================================================================================================//
template <class MethodContainerType, class ObserverRelationType>
BaseIO *RecordingBuilder::addObserveRecorderWithVariableConfig(
    const ScalingConfig &scaling_config, const VariableConfig &variable_config,
    MethodContainerType &main_methods, ObserverRelationType &observer_relation)
{
    if (variable_config.type_ == "Real")
    {
        auto &ob = main_methods.template addObserveRecorder<Real>(
            observer_relation, variable_config.name_);
        ob.getObservedVariable().setScalingRef(scaling_config.getScalingRef(variable_config.name_));
        return &ob;
    }

    if (variable_config.type_ == "Vecd")
    {
        auto &ob = main_methods.template addObserveRecorder<Vecd>(
            observer_relation, variable_config.name_);
        ob.getObservedVariable().setScalingRef(scaling_config.getScalingRef(variable_config.name_));
        return &ob;
    }

    throw std::runtime_error(
        "RecordingBuilder::addObserveRecorderWithVariableConfig: no supported variable type found!");
}
//=================================================================================================//
} // namespace SPH
#endif // RECORDING_BUILDER_HPP
