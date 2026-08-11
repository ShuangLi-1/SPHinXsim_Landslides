#include "continuum_dynamics_builder.h"

#include "material_builder.h"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
BaseDynamics<void> &ContinuumDynamicsBuilder::addAdvectionStepSetup(
    SPHSimulation &sim, MainMethods &main_methods)
{
    auto &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();
    auto &continuum_bodies_config = config_manager.getEntity<StdVec<SPHBodyConfig *>>(
        "ContinuumBodiesConfig");
    auto &advection_step_setup = main_methods.addParticleDynamicsGroup();

    for (const auto &cb : continuum_bodies_config)
    {
        auto &continuum_body = sph_system.getBodyByName<RealBody>(cb->name_);
        advection_step_setup.add(&main_methods.addStateDynamics<fluid_dynamics::AdvectionStepSetup>(
            continuum_body));
    }
    return advection_step_setup;
}
//=================================================================================================//
BaseDynamics<void> &ContinuumDynamicsBuilder::addUpdateParticlePosition(
    SPHSimulation &sim, MainMethods &main_methods)
{
    auto &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();
    auto &continuum_bodies_config = config_manager.getEntity<StdVec<SPHBodyConfig *>>(
        "ContinuumBodiesConfig");
    auto &update_particle_position = main_methods.addParticleDynamicsGroup();

    for (const auto &cb : continuum_bodies_config)
    {
        auto &continuum_body = sph_system.getBodyByName<RealBody>(cb->name_);
        update_particle_position.add(&main_methods.addStateDynamics<fluid_dynamics::UpdateParticlePosition>(
            continuum_body));
    }
    return update_particle_position;
}
//=================================================================================================//
BaseDynamics<void> &ContinuumDynamicsBuilder::addLinearCorrectionMatrix(
    SPHSimulation &sim, MainMethods &main_methods)
{
    auto &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();
    auto &continuum_bodies_config = config_manager.getEntity<StdVec<SPHBodyConfig *>>(
        "ContinuumBodiesConfig");
    auto &linear_correction_matrix = main_methods.addParticleDynamicsGroup();

    for (const auto &cb : continuum_bodies_config)
    {
        std::string body_name = cb->name_;
        auto &inner_relation = sph_system.getRelationByName<Inner<Relation<RealBody>>>(body_name);

        if (!config_manager.hasEntity<PlasticContinuum>(body_name + "PlasticContinuum"))
        {
            auto &continuum_solver_parameters = config_manager.getEntity<
                ContinuumSolverParameters>("ContinuumSolverParameters");
            linear_correction_matrix.add(
                &main_methods.template addInteractionDynamicsWithUpdate<
                    LinearCorrectionMatrix>(inner_relation, continuum_solver_parameters.linear_correction_matrix_coeff_));
        }
    }
    return linear_correction_matrix;
}
//=================================================================================================//
BaseDynamics<void> &ContinuumDynamicsBuilder::addShearForceIntegration(
    SPHSimulation &sim, MainMethods &main_methods)
    {
    auto &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();
    auto &continuum_bodies_config = config_manager.getEntity<StdVec<SPHBodyConfig *>>(
        "ContinuumBodiesConfig");
    auto &shear_force_integration = main_methods.addParticleDynamicsGroup();

    for (const auto &cb : continuum_bodies_config)
    {
        std::string body_name = cb->name_;
        auto &inner_relation = sph_system.getRelationByName<Inner<Relation<RealBody>>>(body_name);
    }
//=================================================================================================//
} // namespace SPH
