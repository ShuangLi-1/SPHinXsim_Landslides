#ifndef FLUID_SIMULATION_BUILDER_HPP
#define FLUID_SIMULATION_BUILDER_HPP

#include "fluid_simulation_builder.h"

#include <cmath>

#include "fluid_dynamics_builder.hpp"
#include "geometry_builder.h"
#include "sph_simulation.h"
#include "thermal_dynamics_builder.hpp"

namespace SPH
{
//=================================================================================================//
using namespace fluid_dynamics;
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void FluidSimulationBuilder::addMainPhysicalTimeStep(
    SPHSimulation &sim, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &fluid_wall_contact)
{
    EntityManager &config_manager = sim.getConfigManager();
    TimeStepper &time_stepper = sim.getSPHSolver().getTimeStepper();

    auto &acoustic_step_1st_half = main_methods.addParticleDynamicsGroup();
    auto &acoustic_step_2nd_half = main_methods.addParticleDynamicsGroup();
    auto &acoustic_time_step = main_methods.template addReduceDynamicsGroup<ReduceMin<Real>>();

    std::string body_name = inner_relation.getSPHBody().Name();
    SPHBody &sph_body = inner_relation.getSPHBody();
    Real cfl = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig").acoustic_cfl_;
    if (sph_body.isMatterMaterial<WeaklyCompressibleFluid>())
    {
        using RiemannSolverType = RiemannSolver<WeaklyCompressibleFluid, WeaklyCompressibleFluid, TruncatedLinear>;
        acoustic_step_1st_half.add(
            &main_methods.template addInteractionDynamicsOneLevel<
                             AcousticStep1stHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
                 .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact));
        acoustic_step_2nd_half.add(
            &main_methods.template addInteractionDynamicsOneLevel<
                             AcousticStep2ndHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
                 .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact));
        acoustic_time_step.add(
            &main_methods.template addReduceDynamics<AcousticTimeStepCK<WeaklyCompressibleFluid>>(sph_body, cfl));
    }

    if (sph_body.isMatterMaterial<WeaklyCompressibleMixture>())
    {
        using RiemannSolverType = RiemannSolver<WeaklyCompressibleMixture, WeaklyCompressibleMixture, TruncatedLinear>;
        acoustic_step_1st_half.add(
            &main_methods.template addInteractionDynamicsOneLevel<
                             AcousticStep1stHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
                 .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact));
        acoustic_step_2nd_half.add(
            &main_methods.template addInteractionDynamicsOneLevel<
                             AcousticStep2ndHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
                 .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact));
        acoustic_time_step.add(
            &main_methods.template addReduceDynamics<AcousticTimeStepCK<WeaklyCompressibleMixture>>(sph_body, cfl));
    }

    if (acoustic_time_step.hasDynamics() && acoustic_step_1st_half.hasDynamics() && acoustic_step_2nd_half.hasDynamics())
    {
        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::MainPhysicalTimeStep, [&]()
            {
                Real dt = time_stepper.incrementPhysicalTime(acoustic_time_step);
                acoustic_step_1st_half.exec(dt);
                simulation_pipeline.run_hooks(SimulationHookPoint::BoundaryCondition);
                acoustic_step_2nd_half.exec(dt); });
    }
    else
    {
        throw std::runtime_error(
            "FluidSimulationBuilder::addMainPhysicalTimeStep: no supported fluid type found!");
    }
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidSimulationBuilder::addDensityRegularization(
    SPHSimulation &sim, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    auto &config_manager = sim.getConfigManager();
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
    SPHBody &sph_body = inner_relation.getSPHBody();
    std::string body_name = sph_body.Name();

    if (sph_body.isMatterMaterial<WeaklyCompressibleFluid>())
    {
        return FluidDynamicsBuilder::buildDensityRegularization<WeaklyCompressibleFluid>(
            sim, main_methods, inner_relation, contact_relation, fluid_solver_config.surface_type_);
    }

    if (sph_body.isMatterMaterial<WeaklyCompressibleMixture>())
    {
        return FluidDynamicsBuilder::buildDensityRegularization<WeaklyCompressibleMixture>(
            sim, main_methods, inner_relation, contact_relation, fluid_solver_config.surface_type_);
    }

    throw std::runtime_error(
        "FluidSimulationBuilder::addDensityRegularization: no supported fluid type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidSimulationBuilder::addLinearCorrectionMatrixWithScope(
    EntityManager &config_manager, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    auto &fluid_linear_correction_matrix = main_methods.addParticleDynamicsGroup();
    fluid_linear_correction_matrix.add(
        &main_methods.template addInteractionDynamicsWithUpdate<LinearCorrectionMatrix>(inner_relation, 0.5)
             .addPostContactInteraction(contact_relation));

    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
    if (fluid_solver_config.surface_type_ == "open_boundary")
    {
        fluid_linear_correction_matrix.add(
            &main_methods.template addStateDynamics<LinearCorrectionMatrixScope, BulkParticles>(
                inner_relation.getSPHBody()));
    }

    return fluid_linear_correction_matrix;
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void FluidSimulationBuilder::buildTransportVelocityFormulationIfNotFreeSurface(
    SPHSimulation &sim, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    EntityManager &config_manager = sim.getConfigManager();

    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
    if (fluid_solver_config.surface_type_ != "free_surface")
    {
        auto &transport_velocity_correction =
            main_methods.template addInteractionDynamics<
                            KernelGradientIntegral, LinearCorrectionCK>(inner_relation)
                .template addPostContactInteraction<Boundary, LinearCorrectionCK>(contact_relation);

        addTransportVelocityCorrection(
            transport_velocity_correction, inner_relation.getSPHBody(), fluid_solver_config);

        auto &initialization_pipeline = sim.getInitializationPipeline();
        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialAfterLinearCorrectionMatrix, [&]()
            { transport_velocity_correction.exec(); });

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::AfterLinearCorrectionMatrix, [&]()
            { transport_velocity_correction.exec(); });
    }
}
//=================================================================================================//
template <class KernelGradientIntegralType>
void FluidSimulationBuilder::addTransportVelocityCorrection(
    KernelGradientIntegralType &kernel_gradient_integral,
    SPHBody &sph_body, FluidSolverConfig &fluid_solver_config)
{
    if (fluid_solver_config.surface_type_ == "confined")
    {
        kernel_gradient_integral.template addPostStateDynamics<
            TransportVelocityCorrectionCK, TruncatedLinear>(sph_body);
        return;
    }

    if (fluid_solver_config.surface_type_ == "open_boundary")
    {
        kernel_gradient_integral.template addPostStateDynamics<
            TransportVelocityCorrectionCK, TruncatedLinear, BulkParticles>(sph_body);
        return;
    }
    throw std::runtime_error(
        "FluidSimulationBuilder::addTransportVelocityCorrection: no supported flow type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void FluidSimulationBuilder::buildViscousForceIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    EntityManager &config_manager = sim.getConfigManager();
    SPHBody &sph_body = inner_relation.getSPHBody();
    if (config_manager.hasEntity<Viscosity>(sph_body.Name() + "Viscosity"))
    {
        auto &viscous_force =
            main_methods.template addInteractionDynamicsWithUpdate<
                            ViscousForceCK, Viscosity, NoKernelCorrectionCK>(inner_relation)
                .template addPostContactInteraction<Wall, Viscosity, NoKernelCorrectionCK>(contact_relation);

        auto &initialization_pipeline = sim.getInitializationPipeline();
        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialAfterLinearCorrectionMatrix, [&]()
            { viscous_force.exec(); });

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::AfterLinearCorrectionMatrix, [&]()
            { viscous_force.exec(); });
    }
}
//=================================================================================================//
template <class MethodContainerType>
void FluidSimulationBuilder::buildParticleDeletionIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, RealBody &real_body)
{
    auto &config_manager = sim.getConfigManager();
    StagePipeline<SimulationHookPoint> &simulation_pipeline = sim.getSimulationPipeline();
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
    if (fluid_solver_config.particle_deletion_)
    {
        auto &particle_deletion = main_methods.template addStateDynamics<
            OutflowParticleDeletion>(real_body);

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleDeletion, [&]()
            { particle_deletion.exec(); });
    }
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void FluidSimulationBuilder::buildSurfaceIndicationIfOpenBoundary(
    SPHSimulation &sim, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    auto &config_manager = sim.getConfigManager();
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");

    if (fluid_solver_config.surface_type_ == "open_boundary")
    {
        auto &fluid_surface_indication =
            main_methods.template addInteractionDynamicsWithUpdate<
                            FreeSurfaceIndicationCK>(inner_relation)
                .addPostContactInteraction(contact_relation);

        auto &initialization_pipeline = sim.getInitializationPipeline();
        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialParticleIndicationTagging, [&]()
            { fluid_surface_indication.exec(); });

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleIndicationTagging, [&]()
            { fluid_surface_indication.exec(); });
    }
}
//=================================================================================================//
template <class MethodContainerType>
void FluidSimulationBuilder::buildParticleSortIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, RealBody &real_body)
{
    auto &config_manager = sim.getConfigManager();
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
    TimeStepper &time_stepper = sim.getSPHSolver().getTimeStepper();

    if (fluid_solver_config.particle_sorting_)
    {
        auto &particle_sort = main_methods.addSortDynamics(real_body);

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleSort, [&]()
            {
                if (time_stepper.getIterationStep() % fluid_solver_config.sort_frequency_ == 0)
                {
                    particle_sort.exec();
                } });
    }
}
//=================================================================================================//
} // namespace SPH
#endif // FLUID_SIMULATION_BUILDER_HPP
