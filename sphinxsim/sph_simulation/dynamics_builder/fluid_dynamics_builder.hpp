#ifndef FLUID_DYNAMICS_BUILDER_HPP
#define FLUID_DYNAMICS_BUILDER_HPP

#include "fluid_dynamics_builder.h"

#include "density_regularization.hpp"

namespace SPH
{
//=================================================================================================//
template <class FluidType, class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidDynamicsBuilder::buildDensityRegularization(
    MethodContainerType &method_container, InnerRelationType &inner_relation,
    ContactRelationType &contact_relation, const std::string &surface_type)
{
    auto &compression_summation = addDensitySummation(
        method_container, inner_relation, contact_relation);

    if (surface_type == "confined")
    {
        return addDensityRegularization<FluidType, Internal>(
            compression_summation, inner_relation.getSPHBody());
    }

    if (surface_type == "free_surface")
    {
        return addDensityRegularization<FluidType, FreeSurface>(
            compression_summation, inner_relation.getSPHBody());
    }

    if (surface_type == "open_boundary")
    {
        return addDensityRegularization<FluidType, Internal, ExcludeBufferParticles>(
            compression_summation, inner_relation.getSPHBody());
    }

    throw std::runtime_error(
        "FluidDynamicsBuilder::buildDensityRegularization: no supported surface type found!");
}
//=================================================================================================//
template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
decltype(auto) FluidDynamicsBuilder::addDensitySummation(
    MethodContainerType &method_container, InnerRelationType &inner_relation,
    ContactRelationType &contact_relation)
{
    return method_container.template addInteractionDynamics<fluid_dynamics::CompressionSummation>(inner_relation)
        .addPostContactInteraction(contact_relation);
}
//=================================================================================================//
template <class FluidType, class FlowType, class... ParticleScopes, class CompressionSummationType>
BaseDynamics<void> &FluidDynamicsBuilder::addDensityRegularization(
    CompressionSummationType &compression_summation, SPHBody &sph_body)
{
    return compression_summation.template addPostStateDynamics<
        fluid_dynamics::DensityRegularization, FluidType, FlowType, ParticleScopes...>(sph_body);
}
//=================================================================================================//
} // namespace SPH
#endif // FLUID_DYNAMICS_BUILDER_HPP
