#ifndef THERMAL_DYNAMICS_BUILDER_HPP
#define THERMAL_DYNAMICS_BUILDER_HPP

#include "thermal_dynamics_builder.h"

#include "material_builder.h"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void ThermalDynamicsBuilder::buildThermalDynamics(
    SPHSimulation &sim, MethodContainerType &method_container,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    auto &config_manager = sim.getConfigManager();
    auto &sph_system = sim.getSPHSystem();
    auto &time_stepper = sim.getSPHSolver().getTimeStepper();

    std::string body_name = inner_relation.getSPHBody().Name();
    RealBody &real_body = sph_system.getBodyByName<RealBody>(body_name);
    auto &thermal_diffusion = config_manager.getEntity<IsotropicDiffusion>(body_name + "ThermalDiffusion");

    auto &diffusion_time_step = method_container.template addReturnDynamics<
        GetDiffusionTimeStepSize>(real_body, &thermal_diffusion);

    auto &runge_kutta_1st_stage =
        method_container.template addInteractionDynamicsOneLevel<
            DiffusionRelaxationCK, RungeKutta1stStage, IsotropicDiffusion, LinearCorrectionCK>(
            inner_relation, &thermal_diffusion);
    auto &runge_kutta_2nd_stage =
        method_container.template addInteractionDynamicsOneLevel<
            DiffusionRelaxationCK, RungeKutta2ndStage, IsotropicDiffusion, LinearCorrectionCK>(
            inner_relation, &thermal_diffusion);

    StdVec<SPHBody *> contact_bodies = contact_relation.getContactBodies();
    StdVec<SPHBody *> dirichlet_bodies;
    StdVec<SPHBody *> neumann_bodies;
    for (SPHBody *contact_body : contact_bodies)
    {
        std::string cb_name = contact_body->Name();
        if (config_manager.hasEntity<ThermalBoundaryConfig>(cb_name))
        {
            auto &bd_config = config_manager.getEntity<ThermalBoundaryConfig>(cb_name);
            if (bd_config.boundary_type == "Dirichlet")
            {
                dirichlet_bodies.push_back(contact_body);
            }

            if (bd_config.boundary_type == "Neumann")
            {
                neumann_bodies.push_back(contact_body);
            }
        }
    }

    if (!dirichlet_bodies.empty())
    {
        auto contact_dirichlet_view = makeRelationView(contact_relation, dirichlet_bodies);
        runge_kutta_1st_stage.template addPostContactInteraction<
            InteractionOnly, Dirichlet<IsotropicDiffusion>, LinearCorrectionCK>(
            contact_dirichlet_view, &thermal_diffusion);
        runge_kutta_2nd_stage.template addPostContactInteraction<
            InteractionOnly, Dirichlet<IsotropicDiffusion>, LinearCorrectionCK>(
            contact_dirichlet_view, &thermal_diffusion);
    }

    if (!neumann_bodies.empty())
    {
        auto contact_neumann_view = makeRelationView(contact_relation, neumann_bodies);
        runge_kutta_1st_stage.template addPostContactInteraction<
            InteractionOnly, Neumann<IsotropicDiffusion>, LinearCorrectionCK>(
            contact_neumann_view, &thermal_diffusion);
        runge_kutta_2nd_stage.template addPostContactInteraction<
            InteractionOnly, Neumann<IsotropicDiffusion>, LinearCorrectionCK>(
            contact_neumann_view, &thermal_diffusion);
    }

    auto &runge_kutta = method_container.addParticleDynamicsGroup();
    runge_kutta.add(&runge_kutta_1st_stage).add(&runge_kutta_2nd_stage);
    auto &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::CouplingSynchronization, [&]()
        { 
          Real dt = time_stepper.getGlobalTimeStepSize();
          time_stepper.integrateMatchedTimeInterval(runge_kutta, dt, diffusion_time_step); });
}
//=================================================================================================//
} // namespace SPH
#endif // THERMAL_DYNAMICS_BUILDER_HPP
