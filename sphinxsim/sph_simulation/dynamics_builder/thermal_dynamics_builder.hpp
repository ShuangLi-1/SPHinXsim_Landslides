#ifndef THERMAL_DYNAMICS_BUILDER_HPP
#define THERMAL_DYNAMICS_BUILDER_HPP

#include "thermal_dynamics_builder.h"

#include "sph_simulation.h"
#include "material_builder.h"

namespace SPH
{
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void ThermalDynamicsBuilder::buildThermalDynamics(
    SPHSimulation &sim, MethodContainerType &method_container,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    EntityManager &config_manager = sim.getConfigManager();
    auto &sph_system = sim.getSPHSystem();
    auto &time_stepper = sim.getSPHSolver().getTimeStepper();

    std::string body_name = inner_relation.getSPHBody().Name();
    RealBody &real_body = sph_system.getBodyByName<RealBody>(body_name);
    auto &thermal_diffusion = config_manager.getEntity<IsotropicDiffusion>(body_name + "ThermalDiffusion");

    auto &diffusion_time_step = method_container.template addReturnDynamics<
        GetDiffusionTimeStepSize>(real_body, &thermal_diffusion);

    auto &runge_kutta = method_container.addParticleDynamicsGroup();

    auto &diffusion_relaxation_1st_half =
        method_container.template addInteractionDynamicsOneLevel<
            DiffusionRelaxationCK, RungeKutta1stStage, IsotropicDiffusion, LinearCorrectionCK>(
            inner_relation, &thermal_diffusion);
    auto &diffusion_relaxation_2nd_half =
        method_container.template addInteractionDynamicsOneLevel<
            DiffusionRelaxationCK, RungeKutta2ndStage, IsotropicDiffusion, LinearCorrectionCK>(
            inner_relation, &thermal_diffusion);

    StdVec<SPHBody *> contact_bodies = contact_relation.getContactBodies();
    StdVec<SPHBody *> contact__dirichlet_bodies;
    StdVec<SPHBody *> contact_neumann_bodies;

    for (SPHBody *contact_body : contact_bodies)
    {
        std::string contact_body_name = contact_body->Name();
        if (config_manager.hasEntity<ThermalBoundaryConfig>(contact_body_name))
        {
            ThermalBoundaryConfig &boundary_config = config_manager.getEntity<ThermalBoundaryConfig>(contact_body_name);
            if (boundary_config.boundary_type == "Dirichlet")
            {
                contact__dirichlet_bodies.push_back(contact_body);
            }

            if (boundary_config.boundary_type == "Neumann")
            {
                contact_neumann_bodies.push_back(contact_body);
            }
        }
    }

    if (!contact__dirichlet_bodies.empty())
    {
        auto contact__dirichlet_view = makeRelationView(contact_relation, contact__dirichlet_bodies);
        diffusion_relaxation_1st_half.template addPostContactInteraction<
            InteractionOnly, Dirichlet<IsotropicDiffusion>, LinearCorrectionCK>(
            contact__dirichlet_view, &thermal_diffusion);
        diffusion_relaxation_2nd_half.template addPostContactInteraction<
            InteractionOnly, Dirichlet<IsotropicDiffusion>, LinearCorrectionCK>(
            contact__dirichlet_view, &thermal_diffusion);
    }

    if (!contact_neumann_bodies.empty())
    {
        auto contact_neumann_view = makeRelationView(contact_relation, contact_neumann_bodies);
        diffusion_relaxation_1st_half.template addPostContactInteraction<
            InteractionOnly, Neumann<IsotropicDiffusion>, LinearCorrectionCK>(
            contact_neumann_view, &thermal_diffusion);
        diffusion_relaxation_2nd_half.template addPostContactInteraction<
            InteractionOnly, Neumann<IsotropicDiffusion>, LinearCorrectionCK>(
            contact_neumann_view, &thermal_diffusion);
    }

    runge_kutta.add(&diffusion_relaxation_1st_half).add(&diffusion_relaxation_2nd_half);
    StagePipeline<SimulationHookPoint> &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::CouplingSynchronization, [&]()
        { 
          Real dt = time_stepper.getGlobalTimeStepSize();
          time_stepper.integrateMatchedTimeInterval(runge_kutta, dt, diffusion_time_step); });
}
//=================================================================================================//
} // namespace SPH
#endif // THERMAL_DYNAMICS_BUILDER_HPP
