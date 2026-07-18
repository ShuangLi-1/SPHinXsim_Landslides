#ifndef FLUID_DYNAMICS_BUILDER_HPP
#define FLUID_DYNAMICS_BUILDER_HPP

#include "fluid_dynamics_builder.h"

#include "density_regularization.hpp"

namespace SPH
{
//=================================================================================================//
using namespace fluid_dynamics;
//=================================================================================================//
template <class FluidType, class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidDynamicsBuilder::buildDensityRegularization(
    MethodContainerType &method_container, InnerRelationType &inner_relation,
    ContactRelationType &contact_relation, const std::string &surface_type)
{
    auto &density_regularization = method_container.addParticleDynamicsGroup();

    density_regularization.add(
        &method_container.template addInteractionDynamics<CompressionSummation>(inner_relation)
             .addPostContactInteraction(contact_relation));

    SPHBody &sph_body = inner_relation.getSPHBody();

    if (surface_type == "confined")
    {
        density_regularization.add(
            &method_container.template addStateDynamics<
                DensityRegularization, FluidType, Internal>(sph_body));
        return density_regularization;
    }

    if (surface_type == "free_surface")
    {
        density_regularization.add(
            &method_container.template addStateDynamics<
                DensityRegularization, FluidType, FreeSurface>(sph_body));
        return density_regularization;
    }

    if (surface_type == "open_boundary")
    {
        density_regularization.add(
            &method_container.template addStateDynamics<
                DensityRegularization, FluidType, Internal, ExcludeBufferParticles>(sph_body));
        return density_regularization;
    }

    throw std::runtime_error(
        "FluidDynamicsBuilder::buildDensityRegularization: no supported surface type found!");
}
//=================================================================================================//
} // namespace SPH
#endif // FLUID_DYNAMICS_BUILDER_HPP
