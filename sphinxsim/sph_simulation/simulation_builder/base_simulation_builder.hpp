#ifndef BASE_SIMULATION_BUILDER_HPP
#define BASE_SIMULATION_BUILDER_HPP

#include "base_simulation_builder.h"

#include "material_builder.h"
#include "recording_builder.hpp"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class IdentifierType>
BaseDynamics<void> &SimulationBuilder::addVariableAssignment(
    MainMethods &main_methods, IdentifierType &identifier,
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
