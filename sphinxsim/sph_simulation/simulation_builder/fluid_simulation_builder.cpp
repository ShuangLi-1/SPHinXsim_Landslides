#include "fluid_simulation_builder.hpp"

#include "base_simulation_builder.hpp"
#include "solid_dynamics_builder.hpp"

#include "region_material_id.h"
#include "composite_solid.h"
#include "traveling_wave_active_strain.h"
namespace SPH
{
//=================================================================================================//
void FluidSimulationBuilder::buildSimulation(SPHSimulation &sim, const json &config)
{
    //----------------------------------------------------------------------
    // SPHSystem and entity manager.
    // Basically, the SPHSystem is the container of all SPH simulation objects,
    // and the entity manager is the container of all simulation setting
    // configurations and external (not SPH) simulation environments.
    //----------------------------------------------------------------------
    SPHSystem &sph_system = sim.defineSPHSystem();
    EntityManager &config_manager = sim.getConfigManager();
    RecordingBuilder &recording_builder = sim.getRecordingBuilder();
    SPHSolver &sph_solver = sim.defineSPHSolver(*this, config);
    //----------------------------------------------------------------------
    // Creating bodies with inital geometry, materials and particles.
    //----------------------------------------------------------------------
    buildFluidBodies(sph_system, config_manager, config.at("fluid_bodies"));
    buildSolidBodies(sph_system, config_manager, config.at("solid_bodies"));
    //----------------------------------------------------------------------
    // Define body relation map.
    // The relations give the topological connections within (inner) a body
    // or with (contact) other bodies within interaction range.
    // Generally, we first define all the inner relations,
    // then the contact relations.
    //----------------------------------------------------------------------
    auto &fluid_body = *sph_system.collectBodies<FluidBody>().front(); // assume only one fluid body for now
    StdVec<SolidBody *> solid_bodies = sph_system.collectBodies<SolidBody>();
    auto &fluid_inner = sph_system.addInnerRelation(fluid_body);
    auto &fluid_wall_contact = sph_system.addContactRelation(fluid_body, solid_bodies);
    //----------------------------------------------------------------------
    // Define the main numerical methods used in the simulation.
    // Note that there may be data dependence on the sequence of constructions.
    //----------------------------------------------------------------------
    auto &main_methods = sph_solver.addParticleMethodContainer(par_ck);
    //----------------------------------------------------------------------
    // Define dependent optional methods using hooking point in stage pipelines.
    //----------------------------------------------------------------------
    buildSurfaceIndicationIfOpenBoundary(sim, main_methods, fluid_inner, fluid_wall_contact);
    //----------------------------------------------------------------------
    // The essential main methods used for the simulation.
    // Generally, the configuration dynamics, such as update cell linked list,
    // update body relations, are defined first.
    //----------------------------------------------------------------------
    auto &solid_cell_linked_list = main_methods.addCellLinkedListDynamics(solid_bodies);
    // Optional per particle material id assignment, driven by the region model
    // given in each solid body configuration.
    auto &material_id_assignment = main_methods.addParticleDynamicsGroup();
    bool has_material_id_assignment = false;
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    for (const auto &solid_config : config.at("solid_bodies"))
    {
        const json &material_config = solid_config.at("material");
        if (!material_config.contains("material_id_regions"))
            continue;

        const json &region_config = material_config.at("material_id_regions");
        std::string body_name = solid_config.at("name").get<std::string>();
        SolidBody *target_body = nullptr;
        for (SolidBody *solid_body : solid_bodies)
        {
            if (solid_body->Name() == body_name)
                target_body = solid_body;
        }
        if (target_body == nullptr)
        {
            throw std::runtime_error("material id regions refer to an unknown solid body: " + body_name);
        }

        StdVec<Real> coefficients;
        for (const auto &coefficient : region_config.at("envelope_coefficients"))
        {
            coefficients.push_back(coefficient.get<Real>());
        }

        Vecd center = Vecd::Zero();
        const json &center_config = region_config.at("center");
        for (int k = 0; k != center.size(); ++k)
        {
            center[k] = scaling_config.jsonToReal(center_config.at(k), "Length");
        }

        Real region_span = scaling_config.jsonToReal(region_config.at("region_span"), "Length");
        Real tip_span = scaling_config.jsonToReal(region_config.at("tip_span"), "Length");
        Real core_thickness = scaling_config.jsonToReal(region_config.at("core_thickness"), "Length");
        Real envelope_offset = scaling_config.jsonToReal(region_config.at("envelope_offset"), "Length");

        material_id_assignment.add(&main_methods.addStateDynamics<PolynomialRegionMaterialId>(
            *target_body, coefficients, center, region_span, tip_span, core_thickness, envelope_offset));
        has_material_id_assignment = true;
    }

    if (has_material_id_assignment)
    {
        sim.getInitializationPipeline().insert_hook(
            InitializationHookPoint::InitialCondition, [&]()
            { material_id_assignment.exec(); });
    }
    // Elastic solid bodies get their own configuration and stress relaxation.
    // Bodies declared rigid are skipped, so purely rigid cases are unaffected.
    for (const auto &solid_config : config.at("solid_bodies"))
    {
        const std::string material_type =
            solid_config.at("material").at("type").get<std::string>();

        if (material_type != "composite_solid")
            continue;

        std::string body_name = solid_config.at("name").get<std::string>();
        RealBody &elastic_body = sph_system.getBodyByName<RealBody>(body_name);

        auto &elastic_inner = sph_system.addInnerRelation(elastic_body);
        auto &elastic_configuration =
            main_methods.addParticleDynamicsGroup()
                .add(&main_methods.addCellLinkedListDynamics(elastic_body))
                .add(&main_methods.addRelationDynamics(elastic_inner));

        const json &material_config = solid_config.at("material");
        if (material_config.contains("active_strain"))
        {
            const json &wave_config = material_config.at("active_strain");
            const json &region_config = material_config.at("material_id_regions");

            Vecd wave_center = Vecd::Zero();
            for (int k = 0; k != wave_center.size(); ++k)
            {
                wave_center[k] = scaling_config.jsonToReal(region_config.at("center").at(k), "Length");
            }
            Real wave_span = scaling_config.jsonToReal(region_config.at("region_span"), "Length");
            Real wave_core = scaling_config.jsonToReal(region_config.at("core_thickness"), "Length");
            // Wave parameters are taken as given; they are not unit scaled.
            Real amplitude = wave_config.at("amplitude").get<Real>();
            Real frequency = wave_config.at("frequency").get<Real>();
            Real wavelength_factor = wave_config.at("wavelength_factor").get<Real>();
            Real start_time = wave_config.at("start_time").get<Real>();

            auto &active_strain = main_methods.addStateDynamics<TravelingWaveActiveStrain>(
            elastic_body, wave_center, wave_span, wave_core,
            amplitude, frequency, wavelength_factor, start_time);

        sim.getSimulationPipeline().insert_hook(
            SimulationHookPoint::CouplingSynchronization, [&]()
            {
                active_strain.exec();

                sim.getSimulationPipeline().insert_hook(
                    SimulationHookPoint::CouplingSynchronization, [&]()
                    {
                        active_strain.exec();
                    });
            });
        }

        auto &elastic_correction_matrix =
            SolidDynamicsBuilder::buildSolidDynamics<CompositeSolidMaterial>(
                sim, main_methods, elastic_inner);

        sim.getInitializationPipeline().insert_hook(
            InitializationHookPoint::InitialCondition, [&]()
            {
                elastic_configuration.exec();
                elastic_correction_matrix.exec();
            });
    }
    auto &fluid_configuration =
        main_methods.addParticleDynamicsGroup()
            .add(&main_methods.addCellLinkedListDynamics(fluid_body))
            .add(&main_methods.addRelationDynamics(fluid_inner, fluid_wall_contact));

    auto &fluid_advection_step_setup = main_methods.addStateDynamics<fluid_dynamics::AdvectionStepSetup>(fluid_body);
    auto &fluid_particle_position = main_methods.addStateDynamics<fluid_dynamics::UpdateParticlePosition>(fluid_body);

    auto &fluid_linear_correction_matrix = addLinearCorrectionMatrixWithScope(
        config_manager, main_methods, fluid_inner, fluid_wall_contact);

    addMainPhysicalTimeStep(sim, main_methods, fluid_inner, fluid_wall_contact);

    auto &fluid_density_regularization = addDensityRegularization(
        sim, main_methods, fluid_inner, fluid_wall_contact);

    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
    auto &fluid_advection_time_step = main_methods.addReduceDynamics<
        fluid_dynamics::AdvectionTimeStepCK>(fluid_body, Real(1), fluid_solver_config.advection_cfl_);
    //----------------------------------------------------------------------
    //	Define time integration method, screen out uput and observation sample rate.
    //----------------------------------------------------------------------
    auto &solver_common_config = config_manager.getEntity<SolverCommonConfig>("SolverCommonConfig");
    auto &time_stepper = sph_solver.getTimeStepper();
    auto &advection_step = time_stepper.addTriggerByInterval(fluid_advection_time_step.exec());
    auto &state_recording_trigger = time_stepper.addTriggerByInterval(solver_common_config.output_interval_);
    time_stepper.setScreeningInterval(solver_common_config.screen_interval_);
    //----------------------------------------------------------------------
    // Define dependent optional methods using hooking point in stage pipelines.
    //----------------------------------------------------------------------
    buildExternalForceIfPresent(sim, main_methods, fluid_body, config);
    buildTransportVelocityFormulationIfNotFreeSurface(sim, main_methods, fluid_inner, fluid_wall_contact);
    buildViscousForceIfPresent(sim, main_methods, fluid_inner, fluid_wall_contact);
    buildThermalDynamicsIfPresent(sim, main_methods, fluid_inner, fluid_wall_contact);
    //----------------------------------------------------------------------
    // Define initial and boundary conditions,
    // particle deletion and sorting if present.
    //----------------------------------------------------------------------
    buildInitialConditionIfPresent(sim, main_methods, config); // use host kernel
    buildBoundaryConditionsIfPresent(sim, main_methods, config);
    buildParticleDeletionIfPresent(sim, main_methods, fluid_body);
    buildParticleSortIfPresent(sim, main_methods, fluid_body);
    //----------------------------------------------------------------------
    // Define state recording for visualization the simulation results.
    //----------------------------------------------------------------------
    auto &body_state_recorder = recording_builder.createBodyStatesRecording(
        sph_system, config_manager, main_methods, config);
    recording_builder.buildObservationIfPresent(sim, main_methods, config);
    //----------------------------------------------------------------------
    //	Define preparation or initialization step before the main integration.
    //----------------------------------------------------------------------
    auto &initialization_pipeline = sim.getInitializationPipeline();
    initialization_pipeline.main_steps.push_back(
        [&]()
        {
            solid_cell_linked_list.exec();
            fluid_configuration.exec();

            initialization_pipeline.run_hooks(InitializationHookPoint::InitialCondition);
            initialization_pipeline.run_hooks(InitializationHookPoint::InitialParticleIndicationTagging);
            fluid_density_regularization.exec();
            fluid_advection_step_setup.exec();
            fluid_linear_correction_matrix.exec();
            initialization_pipeline.run_hooks(InitializationHookPoint::InitialAfterLinearCorrectionMatrix);

            initialization_pipeline.run_hooks(InitializationHookPoint::InitialObservation);
            body_state_recorder.writeToFile();

            initialization_pipeline.run_hooks(InitializationHookPoint::PreSimulationSanityCheck);
        });
    //----------------------------------------------------------------------
    // Define the time integration method.
    // Here we use dual time stepping with acoustic and advection steps.
    // The acoustic step is executed every physical time step, while the advection step is
    // executed at a lower frequency determined by the advection time step.
    // Note that only in acoustic steps the time integration is carried out.
    //----------------------------------------------------------------------
    auto &simulation_pipeline = sim.getSimulationPipeline();

    simulation_pipeline.main_steps.push_back(
        [&]()
        {
            simulation_pipeline.run_hooks(
                SimulationHookPoint::MainPhysicalTimeStep);

            simulation_pipeline.run_hooks(SimulationHookPoint::MainPhysicalTimeStep);

            simulation_pipeline.run_hooks(SimulationHookPoint::CouplingSynchronization);

            simulation_pipeline.run_hooks(
                SimulationHookPoint::CouplingSynchronization);
        });

    simulation_pipeline.main_steps.push_back( // advection or particle configuration step
        [&]()
        {
            if (advection_step(fluid_advection_time_step))
            {
                fluid_particle_position.exec();
                simulation_pipeline.run_hooks(SimulationHookPoint::PositionConstraint);
                time_stepper.incrementIterationStep();

                if (time_stepper.isFirstComputingStep() || time_stepper.isScreeningStep())
                {
                    std::cout << std::fixed << std::setprecision(9)
                              << "N=" << time_stepper.getIterationStep()
                              << "  Time = " << time_stepper.getPhysicalTimeWithScalingRef()
                              << "  advection_dt = " << advection_step.getIntervalWithScalingRef()
                              << "(scaled: " << advection_step.getInterval() << "),"
                              << "  acoustic_dt = " << time_stepper.getGlobalTimeStepSizeWithScalingRef()
                              << "(scaled: " << time_stepper.getGlobalTimeStepSize() << ")"
                              << "\n";
                }

                if (time_stepper.isObservationStep())
                {
                    simulation_pipeline.run_hooks(SimulationHookPoint::Observation);
                }

                if (state_recording_trigger())
                {
                    body_state_recorder.writeToFile();
                }

                simulation_pipeline.run_hooks(SimulationHookPoint::ParticleCreation);
                simulation_pipeline.run_hooks(SimulationHookPoint::ParticleDeletionTagging);
                simulation_pipeline.run_hooks(SimulationHookPoint::ParticleDeletion);
                simulation_pipeline.run_hooks(SimulationHookPoint::ParticleSort);

                solid_cell_linked_list.exec();
                fluid_configuration.exec();
                simulation_pipeline.run_hooks(SimulationHookPoint::ParticleIndicationTagging);
                fluid_density_regularization.exec();
                fluid_advection_step_setup.exec();
                fluid_linear_correction_matrix.exec();
                simulation_pipeline.run_hooks(SimulationHookPoint::AfterLinearCorrectionMatrix);
            }
        });
}
//=================================================================================================//
void FluidSimulationBuilder::parseSolverParameters(EntityManager &config_manager, const json &config)
{
    SimulationBuilder::parseSolverParameters(config_manager, config);
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    if (config.contains("fluid_dynamics"))
    {
        config_manager.emplaceEntity<FluidSolverConfig>(
            "FluidSolverConfig", parseFluidSolverConfig(scaling_config, config.at("fluid_dynamics")));
    }
}
//=================================================================================================//
FluidSolverConfig FluidSimulationBuilder::parseFluidSolverConfig(
    const ScalingConfig &scaling_config, const json &config)
{
    FluidSolverConfig params;
    if (config.contains("acoustic_cfl"))
        params.acoustic_cfl_ = scaling_config.jsonToReal(
            config.at("acoustic_cfl"), "Dimensionless");
    if (config.contains("advection_cfl"))
        params.advection_cfl_ = scaling_config.jsonToReal(
            config.at("advection_cfl"), "Dimensionless");
    if (config.contains("max_velocity_factor"))
        params.max_velocity_factor_ = scaling_config.jsonToReal(
            config.at("max_velocity_factor"), "Dimensionless");
    if (config.contains("surface_type"))
        params.surface_type_ = config.at("surface_type").get<std::string>();
    if (config.contains("particle_sort_frequency"))
    {
        params.particle_sorting_ = true;
        params.sort_frequency_ = config.at("particle_sort_frequency").get<UnsignedInt>();
    }
    return params;
}
//=================================================================================================//
} // namespace SPH
