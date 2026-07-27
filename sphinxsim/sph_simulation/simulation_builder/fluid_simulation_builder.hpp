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
    auto &acoustic_time_step = main_methods.template addReduceDynamicsGroup<ReduceMin>();

    std::string body_name = inner_relation.getSPHBody().Name();
    SPHBody &sph_body = inner_relation.getSPHBody();
    Real cfl = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig").acoustic_cfl_;
    if (sph_body.isMatterMaterial<WeaklyCompressibleFluid>())
    {
        using RiemannSolverType = RiemannSolver<WeaklyCompressibleFluid, WeaklyCompressibleFluid, TruncatedLinear>;
        std::string kernel_correction =
            config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig").kernel_correction_;

        if (kernel_correction == "none")
        {
            acoustic_step_1st_half.add(
                &main_methods.template addInteractionDynamicsOneLevel<AcousticStep1stHalf, AcousticRiemannSolverCK, NoKernelCorrectionCK>(inner_relation)
                    .template addPostContactInteraction<Wall, AcousticRiemannSolverCK, NoKernelCorrectionCK>(fluid_wall_contact));

            acoustic_step_2nd_half.add(
                &main_methods.template addInteractionDynamicsOneLevel<AcousticStep2ndHalf, AcousticRiemannSolverCK, NoKernelCorrectionCK>(inner_relation)
                    .template addPostContactInteraction<Wall, AcousticRiemannSolverCK, NoKernelCorrectionCK>(fluid_wall_contact));
        }
        else
        {
            acoustic_step_1st_half.add(
                &main_methods.template addInteractionDynamicsOneLevel<
                                AcousticStep1stHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
                    .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact));

            acoustic_step_2nd_half.add(
                &main_methods.template addInteractionDynamicsOneLevel<
                                AcousticStep2ndHalf, RiemannSolverType, LinearCorrectionCK>(inner_relation)
                    .template addPostContactInteraction<Wall, RiemannSolverType, LinearCorrectionCK>(fluid_wall_contact));
        }
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

    if (fluid_solver_config.surface_type_ == "free_stream")
    {
        kernel_gradient_integral.template addPostStateDynamics<TransportVelocityCorrectionCK, NoLimiter, BulkParticles>(sph_body);
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
    { // must be oriented box for emitter
        auto &emitter = fluid_body.addBodyPart<OrientedBoxByParticle>(oriented_box);
        auto &inflow_condition = main_methods.addParticleDynamicsGroup();
        inflow_condition.add(&main_methods.template addStateDynamics<
                              EmitterInflowConditionCK, ConstantInflowSpeed>(
            emitter, scaling_config.jsonToReal(config.at("inflow_speed"), "Speed")));

        auto &fix_constraint = main_methods.template addStateDynamics<
            FixConstraintCK>(emitter);
        auto &injection = main_methods.template addStateDynamics<
            EmitterInflowInjectionCK>(emitter);

        fluid_solver_config.emitter_on_ = true; // enable emitter
        if (config.contains("on_schedule"))
        {
            parseScheduledEvents(
                sim, config.at("on_schedule"), fluid_solver_config.emitter_on_);
        }

        if (config_manager.hasEntity<WeaklyCompressibleMultiPhase>(
                body_name + "WeaklyCompressibleMultiPhase"))
        {
            auto &mixture = config_manager.getEntity<WeaklyCompressibleMultiPhase>(
                body_name + "WeaklyCompressibleMultiPhase");

            if (config.contains("multi_species_phases"))
            {
                for (const auto &phase : config.at("multi_species_phases"))
                {
                    std::string phase_name = phase.at("phase_name").get<std::string>();
                    auto &multi_species_phase = mixture.getMultiSpeciesPhaseByName(phase_name);
                    StdVec<Real> mass_fractions = MaterialBuilder::parseMixtureFractions(
                        scaling_config, phase.at("mass_fractions"));

                    inflow_condition.add(
                        &main_methods.template addStateDynamics<
                            VariableAssignment,
                            ConstantMixtureFraction<WeaklyCompressibleMultiSpecies>>(
                            emitter, multi_species_phase, mass_fractions));
                }
            }

            if (config.contains("volume_fractions"))
            {
                StdVec<Real> volume_fractions = MaterialBuilder::parseMixtureFractions(
                    scaling_config, config.at("volume_fractions"));
                inflow_condition.add(
                    &main_methods.template addStateDynamics<
                        VariableAssignment,
                        ConstantMixtureFraction<WeaklyCompressibleMultiPhase>>(
                        emitter, mixture, volume_fractions));
                inflow_condition.add(
                    &main_methods.template addStateDynamics<
                        VariableAssignment,
                        UpdateReferenceDensity<WeaklyCompressibleMultiPhase>>(
                        emitter, mixture));
            }
        }

        if (config_manager.hasEntity<WeaklyCompressibleMultiSpecies>(
                body_name + "WeaklyCompressibleMultiSpecies"))
        {
            auto &mixture = config_manager.getEntity<WeaklyCompressibleMultiSpecies>(
                body_name + "WeaklyCompressibleMultiSpecies");
            if (config.contains("mass_fractions"))
            {
                StdVec<Real> mass_fractions = MaterialBuilder::parseMixtureFractions(
                    scaling_config, config.at("mass_fractions"));
                inflow_condition.add(
                    &main_methods.template addStateDynamics<
                        VariableAssignment,
                        ConstantMixtureFraction<WeaklyCompressibleMultiSpecies>>(
                        emitter, mixture, mass_fractions));

                inflow_condition.add(
                    &main_methods.template addStateDynamics<
                        VariableAssignment,
                        UpdateReferenceDensity<WeaklyCompressibleMultiSpecies>>(
                        emitter, mixture));
            }
        }

        simulation_pipeline.insert_hook(
            SimulationHookPoint::BoundaryCondition, [&]()
            { if(fluid_solver_config.emitter_on_)
                  inflow_condition.exec(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::PositionConstraint, [&]()
            { if(!fluid_solver_config.emitter_on_)
                    fix_constraint.exec(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleCreation, [&]()
            { if(fluid_solver_config.emitter_on_)
                injection.exec(); });

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

        if (config_manager.hasEntity<WeaklyCompressibleMultiSpecies>(
                body_name + "WeaklyCompressibleMultiSpecies"))
        {
            auto &mixture = config_manager.getEntity<WeaklyCompressibleMultiSpecies>(
                body_name + "WeaklyCompressibleMultiSpecies");
            if (config.contains("mass_fractions"))
            {
                StdVec<Real> mass_fractions = MaterialBuilder::parseMixtureFractions(
                    scaling_config, config.at("mass_fractions"));
                bi_directional_bd.template addSupplementaryCondition<
                    ConstantMixtureFraction<WeaklyCompressibleMultiSpecies>>(
                    main_methods, oriented_box_by_cell, mixture, mass_fractions);

                bi_directional_bd.template addSupplementaryCondition<
                    UpdateReferenceDensity<WeaklyCompressibleMultiSpecies>>(
                    main_methods, oriented_box_by_cell, mixture);
            }
        }
        return;
    }
    if (type == "free_stream")
    {
        // Emitter strip injects particles; buffer sponge imposes the inflow ramp and pins the
        // shift of freshly injected particles; disposer marks outflow particles for deletion.
        OrientedBox &buffer_box = config_manager.getEntity<OrientedBox>(config.at("buffer_box").get<std::string>());
        OrientedBox &disposer_box = config_manager.getEntity<OrientedBox>(config.at("disposer_box").get<std::string>());

        auto &emitter = fluid_body.addBodyPart<OrientedBoxByParticle>(oriented_box);
        auto &buffer = fluid_body.addBodyPart<OrientedBoxByCell>(buffer_box);
        auto &disposer = fluid_body.addBodyPart<OrientedBoxByCell>(disposer_box);

        Real target_speed = scaling_config.jsonToReal(config.at("target_speed"), "Speed");
        Real t_ref = scaling_config.jsonToReal(config.at("t_ref"), "Time");
        StartupToConstantInflowSpeed inflow_speed(target_speed, t_ref);

        auto &injection = main_methods.template addStateDynamics<EmitterInflowInjectionCK>(emitter);
        auto &inflow_condition = main_methods.template addStateDynamics<EmitterInflowConditionCK, StartupToConstantInflowSpeed>(buffer, inflow_speed);
        auto &free_stream_condition = main_methods.template addStateDynamics<FreeStreamCondition<StartupToConstantInflowSpeed>>(fluid_body, inflow_speed);
        auto &disposer_indication = main_methods.template addStateDynamics<WithinDisposerIndication>(disposer);
        auto &shift_pin = main_methods.template addStateDynamics<ConstantConstraintCK, Vecd>(buffer, "Displacement", Vecd::Zero());

        fluid_solver_config.particle_deletion_ = true;

        simulation_pipeline.insert_hook(
            SimulationHookPoint::BoundaryCondition, [&]()
            { free_stream_condition.exec(); inflow_condition.exec(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleCreation, [&]()
            { injection.exec(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::ParticleDeletionTagging, [&]()
            { disposer_indication.exec(); });

        simulation_pipeline.insert_hook(
            SimulationHookPoint::AfterLinearCorrectionMatrix, [&]()
            { shift_pin.exec(); });

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
        SPHBody &sph_body = oriented_box_by_cell.getSPHBody();
        std::string body_name = sph_body.Name();
        if (config_manager.hasEntity<WeaklyCompressibleFluid>(body_name + "WeaklyCompressibleFluid"))
        {
            auto &bi_directional_bd = main_methods.template addGeneralDynamics<
                BidirectionalBoundaryCK, LinearCorrectionCK, PressurePrescribed<WeaklyCompressibleFluid>>(
                oriented_box_by_cell, scaling_config.jsonToReal(config.at("pressure"), "Pressure"));
            return bi_directional_bd;
        }

        if (sph_body.isMatterMaterial<WeaklyCompressibleMixture>())
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

    if (fluid_solver_config.surface_type_ == "open_boundary" || fluid_solver_config.surface_type_ == "free_stream")
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
