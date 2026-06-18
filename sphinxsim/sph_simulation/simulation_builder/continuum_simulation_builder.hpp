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
        auto &continuum_solver_parameters = config_manager.getEntity<
            ContinuumSolverParameters>("ContinuumSolverParameters");
        return method_container.template addInteractionDynamicsOneLevel<
                        continuum_dynamics::PlasticAcousticStep2ndHalf,
                        AcousticRiemannSolverCK, NoKernelCorrectionCK>(
            inner_relation, continuum_solver_parameters.plastic_riemann_dissipation_factor_)
            .template addPostContactInteraction<Wall, AcousticRiemannSolverCK, NoKernelCorrectionCK>(contact_relation);
    }

    throw std::runtime_error(
        "ContinuumSimulationBuilder::addAcousticStep2ndHalf: no supported material type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType>
ParticleDynamicsGroup &ContinuumSimulationBuilder::addShearForceIntegration(
    EntityManager &config_manager, MethodContainerType &method_container, InnerRelationType &inner_relation)
{
    auto &continuum_solver_parameters = config_manager.getEntity<
        ContinuumSolverParameters>("ContinuumSolverParameters");
    auto &continuum_shear_force = method_container.addParticleDynamicsGroup();

    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<GeneralContinuum>(body_name + "GeneralContinuum"))
    {
        continuum_shear_force
            .add(&method_container.template addInteractionDynamics<
                  LinearGradient, Vecd>(inner_relation, "Velocity"))
            .add(&method_container.template addInteractionDynamicsOneLevel<
                 continuum_dynamics::ShearIntegration, GeneralContinuum>(
                 inner_relation, continuum_solver_parameters.hourglass_factor_,
                 continuum_solver_parameters.shear_stress_damping_));
        return continuum_shear_force;
    }

    if (config_manager.hasEntity<J2Plasticity>(body_name + "J2Plasticity"))
    {
        continuum_shear_force
            .add(&method_container.template addInteractionDynamics<
                  LinearGradient, Vecd>(inner_relation, "Velocity"))
            .add(&method_container.template addInteractionDynamicsOneLevel<
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
ParticleDynamicsGroup &ContinuumSimulationBuilder::addLinearCorrectionMatrixIfNotPlasticContinuum(
    EntityManager &config_manager, MethodContainerType &method_container, InnerRelationType &inner_relation)
{
    auto &linear_correction_matrix = method_container.addParticleDynamicsGroup();
    std::string body_name = inner_relation.getSPHBody().Name();
    if (!config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        auto &continuum_solver_parameters = config_manager.getEntity<
            ContinuumSolverParameters>("ContinuumSolverParameters");
        linear_correction_matrix.add(
            &method_container.template addInteractionDynamicsWithUpdate<
                LinearCorrectionMatrix>(inner_relation, continuum_solver_parameters.linear_correction_matrix_coeff_));
    }
    return linear_correction_matrix;
}
//=================================================================================================//
template <class MethodContainerType, class ContactRelationType>
ParticleDynamicsGroup &ContinuumSimulationBuilder::addContactRepulsionFactorIfNotPlasticContinuum(
    EntityManager &config_manager, MethodContainerType &method_container, ContactRelationType &contact_relation)
{
    auto &contact_repulsion_factor = method_container.addParticleDynamicsGroup();
    std::string body_name = contact_relation.getSPHBody().Name();
    if (!config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        contact_repulsion_factor.add(
            &method_container.template addInteractionDynamics<
                solid_dynamics::RepulsionFactor>(contact_relation));
    }
    return contact_repulsion_factor;
}
//=================================================================================================//
template <class MethodContainerType, class ContactRelationType>
ParticleDynamicsGroup &ContinuumSimulationBuilder::addContactRepulsionForceIfNotPlasticContinuum(
    EntityManager &config_manager, MethodContainerType &method_container, ContactRelationType &contact_relation)
{
    auto &contact_repulsion_force = method_container.addParticleDynamicsGroup();
    std::string body_name = contact_relation.getSPHBody().Name();
    if (!config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
    {
        auto &continuum_solver_parameters = config_manager.getEntity<
            ContinuumSolverParameters>("ContinuumSolverParameters");
        contact_repulsion_force.add(
            &method_container.template addInteractionDynamicsWithUpdate<
                solid_dynamics::RepulsionForceCK, Wall>(
                contact_relation, continuum_solver_parameters.contact_numerical_damping_));
    }
    return contact_repulsion_force;
}
//=================================================================================================//
template <class HostMethodContainerType, class MethodContainerType,
          class InnerRelationType, class ContactRelationType>
void ContinuumSimulationBuilder::buildPlasticContinuumDynamicsIfPresent(
    SPHSimulation &sim, HostMethodContainerType &host_methods, MethodContainerType &main_methods,
    SPHBody &continuum_body, InnerRelationType &inner_relation,
    ContactRelationType &contact_relation, BodyStatesRecording &body_state_recorder)
{
    EntityManager &config_manager = sim.getConfigManager();
    if (!config_manager.hasEntity<PlasticContinuum>(continuum_body.Name() + "PlasticContinuum"))
    {
        return;
    }

    auto &wall_normal_direction = host_methods.addParticleDynamicsGroup();
    for (auto *solid_body : sim.getSPHSystem().collectBodies<SolidBody>())
    {
        wall_normal_direction.add(
            &host_methods.template addStateDynamics<NormalFromBodyShapeCK>(*solid_body));
    }

    auto &density_regularization =
        main_methods.template addInteractionDynamics<
                        fluid_dynamics::CompressionSummation>(inner_relation)
            .addPostContactInteraction(contact_relation)
            .template addPostStateDynamics<
                fluid_dynamics::DensityRegularization,
                WeaklyCompressibleFluid, FreeSurface>(continuum_body);

    auto &stress_diffusion = main_methods.template addInteractionDynamics<
        continuum_dynamics::StressDiffusionCK>(inner_relation);

    body_state_recorder.addDerivedVariableRecording<
        StateDynamics<execution::ParallelPolicy, continuum_dynamics::VerticalStressCK>>(continuum_body);
    body_state_recorder.addDerivedVariableRecording<
        StateDynamics<execution::ParallelPolicy, continuum_dynamics::AccDeviatoricPlasticStrainCK>>(continuum_body);

    TimeStepper &time_stepper = sim.getSPHSolver().getTimeStepper();
    auto &initialization_pipeline = sim.getInitializationPipeline();
    initialization_pipeline.insert_hook(
        InitializationHookPoint::InitialCondition, [&]()
        { wall_normal_direction.exec(); });
    initialization_pipeline.insert_hook(
        InitializationHookPoint::InitialParticleIndicationTagging, [&]()
        { density_regularization.exec(); });

    auto &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::BeforeAcousticStep1stHalf, [&]()
        { stress_diffusion.exec(time_stepper.getGlobalTimeStepSize()); });
    simulation_pipeline.insert_hook(
        SimulationHookPoint::ParticleIndicationTagging, [&]()
        { density_regularization.exec(); });
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
