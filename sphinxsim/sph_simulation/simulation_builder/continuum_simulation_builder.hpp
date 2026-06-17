#ifndef CONTINUUM_SIMULATION_BUILDER_HPP
#define CONTINUUM_SIMULATION_BUILDER_HPP

#include "continuum_simulation_builder.h"

#include "all_continuum_dynamics_ck.h"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &ContinuumSimulationBuilder::addAcousticStep1stHalf(
    EntityManager &config_manager, MethodContainerType &method_container,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<GeneralContinuum>(body_name + "GeneralContinuum"))
    {
        using RiemannSolverType = RiemannSolver<GeneralContinuum, GeneralContinuum, NoLimiter>;
        return method_container.template addInteractionDynamics<
            fluid_dynamics::AcousticStep1stHalf, OneLevel,
            RiemannSolverType, NoKernelCorrectionCK>(inner_relation);
    }

    if (config_manager.hasEntity<J2Plasticity>(body_name + "J2Plasticity"))
    {
        using RiemannSolverType = RiemannSolver<J2Plasticity, J2Plasticity, NoLimiter>;
        return method_container.template addInteractionDynamics<
            fluid_dynamics::AcousticStep1stHalf, OneLevel,
            RiemannSolverType, NoKernelCorrectionCK>(inner_relation);
    }

    if (config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        return method_container.template addInteractionDynamicsOneLevel<
                        continuum_dynamics::PlasticAcousticStep1stHalf,
                        AcousticRiemannSolverCK, NoKernelCorrectionCK>(inner_relation)
            .template addPostContactInteraction<Wall, AcousticRiemannSolverCK, NoKernelCorrectionCK>(contact_relation);
    }

    throw std::runtime_error(
        "ContinuumSimulationBuilder::addAcousticStep1stHalf: no supported material type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &ContinuumSimulationBuilder::addAcousticStep2ndHalf(
    EntityManager &config_manager, MethodContainerType &method_container,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<GeneralContinuum>(body_name + "GeneralContinuum"))
    {
        using RiemannSolverType = RiemannSolver<GeneralContinuum, GeneralContinuum, NoLimiter>;
        return method_container.template addInteractionDynamics<
            fluid_dynamics::AcousticStep2ndHalf, OneLevel,
            RiemannSolverType, NoKernelCorrectionCK>(inner_relation);
    }

    if (config_manager.hasEntity<J2Plasticity>(body_name + "J2Plasticity"))
    {
        using RiemannSolverType = RiemannSolver<J2Plasticity, J2Plasticity, NoLimiter>;
        return method_container.template addInteractionDynamics<
            fluid_dynamics::AcousticStep2ndHalf, OneLevel,
            RiemannSolverType, NoKernelCorrectionCK>(inner_relation);
    }

    if (config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        return method_container.template addInteractionDynamicsOneLevel<
                        continuum_dynamics::PlasticAcousticStep2ndHalf,
                        AcousticRiemannSolverCK, NoKernelCorrectionCK>(inner_relation)
            .template addPostContactInteraction<Wall, AcousticRiemannSolverCK, NoKernelCorrectionCK>(contact_relation);
    }

    throw std::runtime_error(
        "ContinuumSimulationBuilder::addAcousticStep1stHalf: no supported material type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType>
ParticleDynamicsGroup &ContinuumSimulationBuilder::addShearForceIntegration(
    EntityManager &config_manager, MethodContainerType &method_container, InnerRelationType &inner_relation)
{
    auto &continuum_solver_parameters = config_manager.getEntity<
        ContinuumSolverParameters>("ContinuumSolverParameters");
    auto &continuum_shear_force =
        method_container.addParticleDynamicsGroup()
            .add(&method_container.template addInteractionDynamics<
                  LinearGradient, Vecd>(inner_relation, "Velocity"));

    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<GeneralContinuum>(body_name + "GeneralContinuum"))
    {
        continuum_shear_force.add(
            &method_container.template addInteractionDynamicsOneLevel<
                continuum_dynamics::ShearIntegration, GeneralContinuum>(
                inner_relation, continuum_solver_parameters.hourglass_factor_,
                continuum_solver_parameters.shear_stress_damping_));
        return continuum_shear_force;
    }

    if (config_manager.hasEntity<J2Plasticity>(body_name + "J2Plasticity"))
    {
        continuum_shear_force.add(
            &method_container.template addInteractionDynamicsOneLevel<
                continuum_dynamics::ShearIntegration, J2Plasticity>(
                inner_relation, continuum_solver_parameters.hourglass_factor_,
                continuum_solver_parameters.shear_stress_damping_));

        return continuum_shear_force;
    }

    if (config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        return continuum_shear_force;
    }

    throw std::runtime_error(
        "ContinuumSimulationBuilder::addShearForceIntegration: no supported material type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType>
ParticleDynamicsGroup &ContinuumSimulationBuilder::addStressDiffusionIfPlasticContinuum(
    EntityManager &config_manager, MethodContainerType &method_container, InnerRelationType &inner_relation)
{
    auto &stress_diffusion = method_container.addParticleDynamicsGroup();
    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        stress_diffusion.add(
            &method_container.template addInteractionDynamics<
                continuum_dynamics::StressDiffusionCK>(inner_relation));
    }
    return stress_diffusion;
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
ParticleDynamicsGroup &ContinuumSimulationBuilder::addDensityRegularizationIfPlasticContinuum(
    EntityManager &config_manager, MethodContainerType &method_container,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    auto &density_regularization = method_container.addParticleDynamicsGroup();
    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        density_regularization.add(
            &method_container.template addInteractionDynamics<
                             fluid_dynamics::CompressionSummation>(inner_relation)
                 .addPostContactInteraction(contact_relation)
                 .template addPostStateDynamics<
                     fluid_dynamics::DensityRegularization,
                     WeaklyCompressibleFluid, FreeSurface>(inner_relation.getSPHBody()));
    }
    return density_regularization;
}
//=================================================================================================//
template <class MethodContainerType>
void ContinuumSimulationBuilder::buildWallNormalDirectionIfPlasticContinuum(
    SPHSimulation &sim, MethodContainerType &method_container, SPHBody &continuum_body)
{
    EntityManager &config_manager = sim.getConfigManager();
    if (config_manager.hasEntity<PlasticContinuum>(continuum_body.Name() + "PlasticContinuum"))
    {
        auto &wall_normal_direction = method_container.addParticleDynamicsGroup();
        for (auto *solid_body : sim.getSPHSystem().collectBodies<SolidBody>())
        {
            wall_normal_direction.add(
                &method_container.template addStateDynamics<NormalFromBodyShapeCK>(*solid_body));
        }

        auto &initialization_pipeline = sim.getInitializationPipeline();
        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialCondition, [&]()
            { wall_normal_direction.exec(); });
    }
}
//=================================================================================================//
inline void ContinuumSimulationBuilder::addDerivedVariablesToWriteIfPlasticContinuum(
    EntityManager &config_manager, BodyStatesRecording &body_state_recorder, SPHBody &continuum_body)
{
    if (config_manager.hasEntity<PlasticContinuum>(continuum_body.Name() + "PlasticContinuum"))
    {
        body_state_recorder.addDerivedVariableRecording<
            StateDynamics<execution::ParallelPolicy, continuum_dynamics::VerticalStressCK>>(continuum_body);
        body_state_recorder.addDerivedVariableRecording<
            StateDynamics<execution::ParallelPolicy, continuum_dynamics::AccDeviatoricPlasticStrainCK>>(continuum_body);
    }
}
//=================================================================================================//
template <class MethodContainerType>
void ContinuumSimulationBuilder::buildInitialConditionsIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, const json &config)
{
    EntityManager &config_manager = sim.getConfigManager();
    SPHSystem &sph_system = sim.getSPHSystem();
    TimeStepper &time_stepper = sim.getSPHSolver().getTimeStepper();

    if (config_manager.hasEntity<RestartConfig>("RestartConfig"))
    {
        auto &restart_config = config_manager.getEntity<RestartConfig>("RestartConfig");
        sph_system.setRestartStep(restart_config.restore_step_);
        auto &restart_io = main_methods.template addIODynamics<RestartIOCK>(
            sph_system, restart_config.summary_enabled_);

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::ExtraOutput, [&]()
            { 
                if (time_stepper.getIterationStep() % restart_config.save_interval_ == 0)
                {
                    restart_io.writeToFile(time_stepper.getIterationStep());
                } });

        auto &initialization_pipeline = sim.getInitializationPipeline();
        if (restart_config.restore_step_ != 0)
        {
            initialization_pipeline.insert_hook(
                InitializationHookPoint::InitialCondition, [&]()
                { 
                    time_stepper.setRestartStep(restart_config.restore_step_);
                    restart_io.readRestartFiles(restart_config.restore_step_); });
        }
    }
}
//=================================================================================================//
} // namespace SPH
#endif // CONTINUUM_SIMULATION_BUILDER_HPP
