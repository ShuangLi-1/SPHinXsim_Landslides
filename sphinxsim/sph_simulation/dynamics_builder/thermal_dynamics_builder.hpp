#ifndef THERMAL_DYNAMICS_BUILDER_HPP
#define THERMAL_DYNAMICS_BUILDER_HPP

#include "thermal_dynamics_builder.h"

#include "sph_simulation.h"

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
