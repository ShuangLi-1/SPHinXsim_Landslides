#ifndef THERMAL_DYNAMICS_BUILDER_HPP
#define THERMAL_DYNAMICS_BUILDER_HPP

#include "thermal_dynamics_builder.h"

#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
void ThermalDynamicsBuilder::buildThermalDynamics(
    SPHSimulation &sim, MethodContainerType &main_methods,
    InnerRelationType &inner_relation, ContactRelationType &contact_relation)
{
    EntityManager &config_manager = sim.getConfigManager();
    auto &sph_system = sim.getSPHSystem();

    std::string body_name = inner_relation.getSPHBody().Name();
    RealBody &real_body = sph_system.getBodyByName<RealBody>(body_name);
    auto &thermal_diffusion = config_manager.getEntity<IsotropicDiffusion>(body_name + "ThermalDiffusion");

    auto &diffusion_time_step = main_methods.template addReturnDynamics<
        GetDiffusionTimeStepSize>(real_body, &thermal_diffusion);

    StagePipeline<SimulationHookPoint> &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::CouplingSynchronization, [&]()
        { diffusion_time_step.exec(); });
}
//=================================================================================================//
} // namespace SPH
#endif // THERMAL_DYNAMICS_BUILDER_HPP
