#ifndef FLUID_SIMULATION_BUILDER_HPP
#define FLUID_SIMULATION_BUILDER_HPP

#include "fluid_simulation_builder.h"

#include <cmath>

#include "geometry_builder.h"
#include "sph_simulation.h"
#include "thermal_dynamics_builder.hpp"

namespace SPH
{
//=================================================================================================//
using namespace fluid_dynamics;
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidSimulationBuilder::addAcousticStep1stHalf(
    EntityManager &config_manager, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &fluid_wall_contact)
{
    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<WeaklyCompressibleFluid>(body_name + "WeaklyCompressibleFluid"))
    {
        using RiemannSolverType = RiemannSolver<WeaklyCompressibleFluid, WeaklyCompressibleFluid, TruncatedLinear>;
        return main_methods.template addInteractionDynamicsOneLevel<
                               AcousticStep1stHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
            .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact);
    }

    if (config_manager.hasEntity<WeaklyCompressibleMixture>(body_name + "WeaklyCompressibleMixture"))
    {
        using RiemannSolverType = RiemannSolver<WeaklyCompressibleMixture, WeaklyCompressibleMixture, TruncatedLinear>;
        return main_methods.template addInteractionDynamicsOneLevel<
                               AcousticStep1stHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
            .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact);
    }

    throw std::runtime_error(
        "FluidSimulationBuilder::addAcousticStep1stHalf: no supported fluid type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidSimulationBuilder::addAcousticStep2ndHalf(
    EntityManager &config_manager, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &fluid_wall_contact)
{
    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<WeaklyCompressibleFluid>(body_name + "WeaklyCompressibleFluid"))
    {
        using RiemannSolverType = RiemannSolver<WeaklyCompressibleFluid, WeaklyCompressibleFluid, TruncatedLinear>;
        return main_methods.template addInteractionDynamicsOneLevel<
                               AcousticStep2ndHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
            .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact);
    }

    if (config_manager.hasEntity<WeaklyCompressibleMixture>(body_name + "WeaklyCompressibleMixture"))
    {
        using RiemannSolverType = RiemannSolver<WeaklyCompressibleMixture, WeaklyCompressibleMixture, TruncatedLinear>;
        return main_methods.template addInteractionDynamicsOneLevel<
                               AcousticStep2ndHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
            .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact);
    }

    throw std::runtime_error(
        "FluidSimulationBuilder::addAcousticStep2ndHalf: no supported fluid type found!");
}
//=================================================================================================//
template <class MethodContainerType>
BaseDynamics<Real> &FluidSimulationBuilder::addAcousticTimeStep(
    EntityManager &config_manager, MethodContainerType &main_methods, RealBody &real_body)
{
    std::string body_name = real_body.Name();
    Real cfl = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig").acoustic_cfl_;
    if (config_manager.hasEntity<WeaklyCompressibleFluid>(body_name + "WeaklyCompressibleFluid"))
    {
        return main_methods.template addReduceDynamics<AcousticTimeStepCK<WeaklyCompressibleFluid>>(real_body, cfl);
    }

    if (config_manager.hasEntity<WeaklyCompressibleMixture>(body_name + "WeaklyCompressibleMixture"))
    {
        return main_methods.template addReduceDynamics<AcousticTimeStepCK<WeaklyCompressibleMixture>>(real_body, cfl);
    }

    throw std::runtime_error(
        "FluidSimulationBuilder::addAcousticTimeStep: no supported fluid type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidSimulationBuilder::addDensitySummationAndRegularization(
    EntityManager &config_manager, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    auto &compression_summation =
        main_methods.template addInteractionDynamics<CompressionSummation>(inner_relation)
            .addPostContactInteraction(contact_relation);

    SPHBody &sph_body = inner_relation.getSPHBody();
    std::string body_name = sph_body.Name();
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
    std::string surface_type = fluid_solver_config.surface_type_;

    if (config_manager.hasEntity<WeaklyCompressibleFluid>(body_name + "WeaklyCompressibleFluid"))
    {
        return addDensityRegularization<WeaklyCompressibleFluid>(
            compression_summation, sph_body, surface_type);
    }

    if (config_manager.hasEntity<WeaklyCompressibleMixture>(body_name + "WeaklyCompressibleMixture"))
    {
        return addDensityRegularization<WeaklyCompressibleMixture>(
            compression_summation, sph_body, surface_type);
    }

    throw std::runtime_error(
        "FluidSimulationBuilder::addDensitySummationAndRegularization: no supported fluid type found!");
}
//=================================================================================================//
template <class FluidType, class CompressionSummationType>
BaseDynamics<void> &FluidSimulationBuilder::addDensityRegularization(
    CompressionSummationType &compression_summation, SPHBody &sph_body, std::string &surface_type)
{
    if (surface_type == "confined")
    {
        return compression_summation.template addPostStateDynamics<
            DensityRegularization, FluidType, Internal>(sph_body);
    }

    if (surface_type == "free_surface")
    {
        return compression_summation.template addPostStateDynamics<
            DensityRegularization, FluidType, FreeSurface>(sph_body);
    }

    if (surface_type == "open_boundary")
    {
        return compression_summation.template addPostStateDynamics<
            DensityRegularization, FluidType, Internal, ExcludeBufferParticles>(sph_body);
    }

    throw std::runtime_error(
        "FluidSimulationBuilder::addDensityRegularization: no supported surface type found!");
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
            InitializationHookPoint::InitialAfterAdvectionStepSetup, [&]()
            { transport_velocity_correction.exec(); });

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::AfterAdvectionStepSetup, [&]()
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
            InitializationHookPoint::InitialAfterAdvectionStepSetup, [&]()
            { viscous_force.exec(); });

        auto &simulation_pipeline = sim.getSimulationPipeline();
        simulation_pipeline.insert_hook(
            SimulationHookPoint::AfterAdvectionStepSetup, [&]()
            { viscous_force.exec(); });
    }
}
//=================================================================================================//
template <class MethodContainerType>
void FluidSimulationBuilder::buildBoundaryConditionsIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, const json &config)
{
    if (config.contains("fluid_boundary_conditions"))
    {
        for (const auto &bd : config.at("fluid_boundary_conditions"))
        {
            addBoundaryCondition(sim, main_methods, bd);
        }
    }
}
//=================================================================================================//
template <class MethodContainerType>
void FluidSimulationBuilder::addBoundaryCondition(
    SPHSimulation &sim, MethodContainerType &main_methods, const json &config)
{
    StagePipeline<InitializationHookPoint> &initialization_pipeline = sim.getInitializationPipeline();
    StagePipeline<SimulationHookPoint> &simulation_pipeline = sim.getSimulationPipeline();
    EntityManager &config_manager = sim.getConfigManager();
    TimeStepper &time_stepper = sim.getSPHSolver().getTimeStepper();
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");

    const std::string body_name = config.at("body_name").get<std::string>();
    FluidBody &fluid_body = sim.getSPHSystem().getBodyByName<FluidBody>(body_name);
    OrientedBox &oriented_box = config_manager.getEntity<OrientedBox>(
        config.at("oriented_box").get<std::string>());
    const std::string type = config.at("type").get<std::string>();

    if (type == "emitter")
    { // must be aligned box for emitter
        auto &emitter = fluid_body.addBodyPart<OrientedBoxByParticle>(oriented_box);
        auto &inflow_condition = main_methods.template addStateDynamics<
            EmitterInflowConditionCK, ConstantInflowSpeed>(
            emitter, scaling_config.jsonToReal(config.at("inflow_speed"), "Speed"));
        auto &injection = main_methods.template addStateDynamics<
            EmitterInflowInjectionCK>(emitter);

        simulation_pipeline.insert_hook(
            SimulationHookPoint::BoundaryCondition, [&]()
            { inflow_condition.exec(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleCreation, [&]()
            { injection.exec(); });

        return;
    }

    if (type == "bi_directional")
    {
        auto &oriented_box_by_cell = fluid_body.addBodyPart<OrientedBoxByCell>(oriented_box);
        auto &bi_directional_bd = createBiDirectionBoundary(
            oriented_box_by_cell, config_manager, main_methods, config);

        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialParticleIndicationTagging, [&]()
            { bi_directional_bd.tagBufferParticles(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::BoundaryCondition, [&]()
            {   
                Real dt = time_stepper.getGlobalTimeStepSize();
                bi_directional_bd.applyBoundaryCondition(dt); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleCreation, [&]()
            { bi_directional_bd.injectParticles(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleDeletionTagging, [&]()
            { bi_directional_bd.indicateOutFlowParticles(); });
        fluid_solver_config.particle_deletion_ = true; // enable particle deletion

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleIndicationTagging, [&]()
            { bi_directional_bd.tagBufferParticles(); });

        if (config_manager.hasEntity<WeaklyCompressibleMixture>(
                body_name + "WeaklyCompressibleMixture"))
        {
            auto &mixture = config_manager.getEntity<WeaklyCompressibleMixture>(
                body_name + "WeaklyCompressibleMixture");
            if (config.contains("mass_fractions"))
            {
                StdVec<Real> mass_fractions;
                Real mass_fraction_sum = 0.0;
                for (const auto &mf : config.at("mass_fractions"))
                {
                    Real fraction = scaling_config.jsonToReal(mf, "Dimensionless");
                    if (fraction < 0.0 || fraction > 1.0)
                    {
                        throw std::runtime_error(
                            "FluidSimulationBuilder::addBoundaryCondition: mass_fractions values must be in [0, 1]");
                    }
                    mass_fractions.push_back(fraction);
                    mass_fraction_sum += fraction;
                }

                if (mass_fractions.empty())
                {
                    throw std::runtime_error(
                        "FluidSimulationBuilder::addBoundaryCondition: mass_fractions must be non-empty when provided");
                }

                if (std::abs(mass_fraction_sum - 1.0) > 1.0e-6)
                {
                    throw std::runtime_error(
                        "FluidSimulationBuilder::addBoundaryCondition: mass_fractions must sum to 1.0");
                }
                bi_directional_bd.template addSupplementaryCondition<
                    typename MethodContainerType::ExPolicy, PrescribedReferenceDensity>(
                    oriented_box_by_cell, mixture, mass_fractions);
            }
        }
        return;
    }
    throw std::runtime_error(
        "FluidSimulationBuilder::buildBoundaryConditionsIfPresent: unsupported: " + type);
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
template <class MethodContainerType>
AbstractBidirectionalBoundary &FluidSimulationBuilder::createBiDirectionBoundary(
    OrientedBoxByCell &oriented_box_by_cell, EntityManager &config_manager,
    MethodContainerType &main_methods, const json &config)
{
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    if (config.contains("pressure"))
    {
        std::string body_name = oriented_box_by_cell.getSPHBody().Name();
        if (config_manager.hasEntity<WeaklyCompressibleFluid>(body_name + "WeaklyCompressibleFluid"))
        {
            auto &bi_directional_bd = main_methods.template addGeneralDynamics<
                BidirectionalBoundaryCK, LinearCorrectionCK, PressurePrescribed<WeaklyCompressibleFluid>>(
                oriented_box_by_cell, scaling_config.jsonToReal(config.at("pressure"), "Pressure"));
            return bi_directional_bd;
        }

        if (config_manager.hasEntity<WeaklyCompressibleMixture>(body_name + "WeaklyCompressibleMixture"))
        {
            auto &bi_directional_bd = main_methods.template addGeneralDynamics<
                BidirectionalBoundaryCK, LinearCorrectionCK, PressurePrescribed<WeaklyCompressibleMixture>>(
                oriented_box_by_cell, scaling_config.jsonToReal(config.at("pressure"), "Pressure"));
            return bi_directional_bd;
        }
    }

    throw std::runtime_error(
        "FluidSimulationBuilder::createBiDirectionBoundary: unsupported boundary condition type");
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
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void FluidSimulationBuilder::buildThermalDynamicsIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    auto &config_manager = sim.getConfigManager();
    std::string body_name = inner_relation.getSPHBody().Name();
    if (config_manager.hasEntity<IsotropicDiffusion>(body_name + "ThermalDiffusion"))
    {
        ThermalDynamicsBuilder::buildThermalDynamics(sim, main_methods, inner_relation, contact_relation);
    }
}
//=================================================================================================//
} // namespace SPH
#endif // FLUID_SIMULATION_BUILDER_HPP
