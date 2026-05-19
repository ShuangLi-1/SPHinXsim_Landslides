#ifndef BASE_SIMULATION_BUILDER_HPP
#define BASE_SIMULATION_BUILDER_HPP

#include "base_simulation_builder.h"

#include "material_builder.h"
#include "recording_builder.hpp"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class MethodContainerType>
void SimulationBuilder::buildExternalForceIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, SPHBody &real_body, const json &config)
{
    auto &config_manager = sim.getConfigManager();
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    auto &initialization_pipeline = sim.getInitializationPipeline();

    if (config.contains("gravity"))
    {
        auto &constant_gravity =
            main_methods.template addStateDynamics<GravityForceCK<Gravity>>(
                real_body, Gravity(scaling_config.jsonToVecd(config.at("gravity"), "Acceleration")));

        initialization_pipeline.insert_hook(
            InitializationHookPoint::InitialCondition, [&]()
            { constant_gravity.exec(); });
    }
}
//=================================================================================================//
template <class MethodContainerType>
void SimulationBuilder::buildInitialConditionIfPresent(
    SPHSimulation &sim, MethodContainerType &main_methods, const json &config)
{
    SPHSystem &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    auto &initialization_pipeline = sim.getInitializationPipeline();

    for (const auto &ic : config)
    {
        const std::string name = ic.at("name").get<std::string>();
        auto &real_body = sph_system.getBodyByName<RealBody>(name);
        for (const auto &assignment : ic.at("assignments"))
        {
            std::string region_name = assignment.at("region").get<std::string>();
            if (region_name == "All")
            {
                auto &dynamics = addVariableAssignment(main_methods, real_body, scaling_config, assignment);

                initialization_pipeline.insert_hook(
                    InitializationHookPoint::InitialCondition, [&]()
                    { dynamics.exec(); });
            }
            else
            {
                auto &region_shape = config_manager.getEntity<Shape>(region_name);
                auto &body_region = real_body.template addBodyPart<BodyRegionByParticle>(region_shape);
                auto &dynamics = addVariableAssignment(main_methods, body_region, scaling_config, assignment);

                initialization_pipeline.insert_hook(
                    InitializationHookPoint::InitialCondition, [&]()
                    { dynamics.exec(); });
            }
        }
    }
}
//=================================================================================================//
template <class MethodContainerType, class IdentifierType>
BaseDynamics<void> &SimulationBuilder::addVariableAssignment(
    MethodContainerType &main_methods, IdentifierType &identifier,
    const ScalingConfig &scaling_config, const json &config)
{
    VariableConfig var_config = parseVariableConfig(config.at("variable"));
    if (var_config.type_ == "Real")
    {
        Real value = scaling_config.jsonToReal(config.at("value"), var_config.name_);
        return main_methods.template addStateDynamics<VariableAssignment, ConstantValue<Real>>(
            identifier, var_config.name_, value);
    }
    else if (var_config.type_ == "Vecd")
    {
        Vecd value = scaling_config.jsonToVecd(config.at("value"), var_config.name_);
        return main_methods.template addStateDynamics<VariableAssignment, ConstantValue<Vecd>>(
            identifier, var_config.name_, value);
    }
    else
    {
        throw std::runtime_error("Unsupported variable type in variable assignment: " + var_config.type_);
    }
}
//=================================================================================================//
} // namespace SPH
#endif // BASE_SIMULATION_BUILDER_HPP
