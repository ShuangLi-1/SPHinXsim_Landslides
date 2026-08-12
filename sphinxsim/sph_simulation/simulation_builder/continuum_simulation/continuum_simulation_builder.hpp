#ifndef CONTINUUM_SIMULATION_BUILDER_HPP
#define CONTINUUM_SIMULATION_BUILDER_HPP

#include "continuum_simulation_builder.h"

#include "all_continuum_dynamics_ck.h"
#include "fluid_dynamics_builder.hpp"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class InnerRelationType>
void ContinuumSimulationBuilder::buildShearForceIntegrationIfPresent(
    SPHSimulation &sim, MainMethods &main_methods, InnerRelationType &inner_relation)
{
    std::string body_name = inner_relation.getSPHBody().Name();
    auto &config_manager = sim.getConfigManager();

    if (config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
        return;

    auto &time_stepper = sim.getSPHSolver().getTimeStepper();
    auto &continuum_shear_force = main_methods.addParticleDynamicsGroup();
    auto &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::BeforeMainPhysicalTimeStep, [&]()
        {   Real dt = time_stepper.getGlobalTimeStepSize(); 
            continuum_shear_force.exec(dt); });

    continuum_shear_force.add(&main_methods.template addInteractionDynamics<
                               LinearGradient, Vecd>(inner_relation, "Velocity"));

    auto &continuum_solver_parameters = config_manager.getEntity<
        ContinuumSolverParameters>("ContinuumSolverParameters");

    if (config_manager.hasEntity<GeneralContinuum>(body_name + "GeneralContinuum"))
    {
        continuum_shear_force
            .add(&main_methods.template addInteractionDynamicsOneLevel<
                  continuum_dynamics::ShearIntegration, GeneralContinuum>(
                inner_relation, continuum_solver_parameters.hourglass_factor_,
                continuum_solver_parameters.shear_stress_damping_));
        return;
    }

    if (config_manager.hasEntity<J2Plasticity>(body_name + "J2Plasticity"))
    {
        continuum_shear_force
            .add(&main_methods.template addInteractionDynamicsOneLevel<
                  continuum_dynamics::ShearIntegration, J2Plasticity>(
                inner_relation, continuum_solver_parameters.hourglass_factor_,
                continuum_solver_parameters.shear_stress_damping_));
        return;
    }

    throw std::runtime_error(
        "ContinuumSimulationBuilder::buildShearForceIntegrationIfPresent: no supported material type found!");
}
//=================================================================================================//
template <class ContactRelationType>
void ContinuumSimulationBuilder::buildContactRepulsionIfPresent(
    SPHSimulation &sim, MainMethods &main_methods, ContactRelationType &contact_relation)
{
    auto &config_manager = sim.getConfigManager();
    std::string body_name = contact_relation.getSPHBody().Name();
    if (config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
        return;

    if (config_manager.hasEntity<GeneralContinuum>(body_name + "GeneralContinuum") ||
        config_manager.hasEntity<J2Plasticity>(body_name + "J2Plasticity"))
    {

        auto &contact_repulsion_factor = main_methods.template addInteractionDynamics<
            solid_dynamics::RepulsionFactor>(contact_relation);

        auto &continuum_solver_parameters = config_manager.getEntity<
            ContinuumSolverParameters>("ContinuumSolverParameters");
        auto &contact_repulsion_force =
            main_methods.template addInteractionDynamicsWithUpdate<
                solid_dynamics::RepulsionForceCK, Wall>(
                contact_relation, continuum_solver_parameters.contact_numerical_damping_);

        auto &initialization_pipeline = sim.getInitializationPipeline();
        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialAfterLinearCorrectionMatrix, [&]()
            { contact_repulsion_factor.exec(); });

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::BeforeMainPhysicalTimeStep, [&]()
            { contact_repulsion_force.exec(); });
        simulation_pipeline.insert_hook(
            SimulationHookPoint::AfterLinearCorrectionMatrix, [&]()
            { contact_repulsion_factor.exec(); });

        return;
    }

    throw std::runtime_error(
        "ContinuumSimulationBuilder::buildContactRepulsionIfPresent: no supported material type found!");
}
//=================================================================================================//
template <class InnerRelationType, class ContactRelationType>
void ContinuumSimulationBuilder::buildDensityRegularizationIfPresent(
    SPHSimulation &sim, MainMethods &main_methods,
    SPHBody &continuum_body, InnerRelationType &inner_relation,
    ContactRelationType &contact_relation)
{
    EntityManager &config_manager = sim.getConfigManager();
    if (!config_manager.hasEntity<PlasticContinuum>(continuum_body.Name() + "PlasticContinuum"))
        return;

    auto &continuum_solver_parameters = config_manager.getEntity<
        ContinuumSolverParameters>("ContinuumSolverParameters");
    auto &density_regularization =
        FluidDynamicsBuilder::buildDensityRegularization<WeaklyCompressibleFluid>(
            sim, main_methods, inner_relation, contact_relation,
            continuum_solver_parameters.surface_type_);

    auto &initialization_pipeline = sim.getInitializationPipeline();
    initialization_pipeline.insert_hook(
        InitializationHookPoint::AfterInitialCondition, [&]()
        { density_regularization.exec(); });

    auto &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::AfterUpdateConfiguration, [&]()
        { density_regularization.exec(); });
}
//=================================================================================================//
template <class InnerRelationType>
void ContinuumSimulationBuilder::buildStressDiffusionIfPresent(
    SPHSimulation &sim, MainMethods &main_methods,
    SPHBody &continuum_body, InnerRelationType &inner_relation,
    BodyStatesRecording &body_state_recorder)
{
    EntityManager &config_manager = sim.getConfigManager();
    if (config_manager.hasEntity<PlasticContinuum>(continuum_body.Name() + "PlasticContinuum"))
    {
        auto &stress_diffusion = main_methods.template addInteractionDynamics<
            continuum_dynamics::StressDiffusionCK>(inner_relation);

        body_state_recorder.addDerivedVariableRecording<
            StateDynamics<execution::ParallelPolicy, continuum_dynamics::VerticalStressCK>>(continuum_body);
        body_state_recorder.addDerivedVariableRecording<
            StateDynamics<execution::ParallelPolicy, continuum_dynamics::AccDeviatoricPlasticStrainCK>>(continuum_body);

        auto &time_stepper = sim.getSPHSolver().getTimeStepper();
        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::BeforeMainPhysicalTimeStep, [&]()
            {   Real dt = time_stepper.getGlobalTimeStepSize();
                stress_diffusion.exec(dt); });
    }
}
//=================================================================================================//
} // namespace SPH
#endif // CONTINUUM_SIMULATION_BUILDER_HPP
