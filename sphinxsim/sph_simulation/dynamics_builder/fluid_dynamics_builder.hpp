#ifndef FLUID_DYNAMICS_BUILDER_HPP
#define FLUID_DYNAMICS_BUILDER_HPP

#include "fluid_dynamics_builder.h"

#include "all_shared_fluid_dynamics_ck.h"

namespace SPH
{
//=================================================================================================//
template <class FluidType, class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidDynamicsBuilder::addDensitySummationAndRegularization(
    MethodContainerType &method_container, InnerRelationType &inner_relation,
    ContactRelationType &contact_relation, SPHBody &sph_body,
    const std::string &surface_type)
{
    auto &compression_summation =
        method_container.template addInteractionDynamics<fluid_dynamics::CompressionSummation>(inner_relation)
            .addPostContactInteraction(contact_relation);

    return addDensityRegularization<FluidType>(
        compression_summation, sph_body, surface_type);
}
//=================================================================================================//
template <class FluidType, class CompressionSummationType>
BaseDynamics<void> &FluidDynamicsBuilder::addDensityRegularization(
    CompressionSummationType &compression_summation, SPHBody &sph_body,
    const std::string &surface_type)
{
    if (surface_type == "confined")
    {
        return compression_summation.template addPostStateDynamics<
            fluid_dynamics::DensityRegularization, FluidType, Internal>(sph_body);
    }

    if (surface_type == "free_surface")
    {
        return compression_summation.template addPostStateDynamics<
            fluid_dynamics::DensityRegularization, FluidType, FreeSurface>(sph_body);
    }

    if (surface_type == "open_boundary")
    {
        return compression_summation.template addPostStateDynamics<
            fluid_dynamics::DensityRegularization, FluidType, Internal, ExcludeBufferParticles>(sph_body);
    }

    throw std::runtime_error(
        "FluidDynamicsBuilder::addDensityRegularization: no supported surface type found!");
}
//=================================================================================================//
} // namespace SPH
#endif // FLUID_DYNAMICS_BUILDER_HPP
