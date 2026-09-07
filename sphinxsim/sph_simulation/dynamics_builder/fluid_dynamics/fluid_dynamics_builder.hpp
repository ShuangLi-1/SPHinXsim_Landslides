#ifndef FLUID_DYNAMICS_BUILDER_HPP
#define FLUID_DYNAMICS_BUILDER_HPP

#include "fluid_dynamics_builder.h"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
using namespace fluid_dynamics;
//=================================================================================================//
template <class FluidType, class FluidBodyType>
BaseDynamics<void> &FluidDynamicsBuilder::addDensityRegularizationForOneBody(
    MainMethods &main_methods, FluidBodyType &fluid_body, const std::string &surface_type)
{
    if (surface_type == "confined")
    {
        return main_methods.template addStateDynamics<
            DensityRegularization, FluidType, Internal>(fluid_body);
    }

    if (surface_type == "free_surface")
    {
        return main_methods.template addStateDynamics<
            DensityRegularization, FluidType, FreeSurface>(fluid_body);
    }

    if (surface_type == "open_boundary")
    {
        return main_methods.template addStateDynamics<
            DensityRegularization, FluidType, Internal, ExcludeBufferParticles>(fluid_body);
    }

    if (surface_type == "free_stream")
    {
        return main_methods.template addStateDynamics<
            DensityRegularization, FluidType, FreeStream>(fluid_body);
    }

    throw std::runtime_error(
        "FluidDynamicsBuilder::addDensityRegularizationForOneBody: no supported surface type found!");
}
//=================================================================================================//
template <template <typename...> class AcousticHalfStepForOneBodyType, class InnerRelationType>
BaseDynamics<void> &FluidDynamicsBuilder::addAcousticHalfStepForOneBody(
    SPHSimulation &sim, InnerRelationType &inner_relation, MainMethods &main_methods)
{
    auto &config_manager = sim.getConfigManager();
    auto &sph_body = inner_relation.getSPHBody();
    std::string body_name = sph_body.Name();
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");

    if (sph_body.template isMatterMaterial<WeaklyCompressibleFluid>())
    {
        using RiemannSolverType =
            RiemannSolver<WeaklyCompressibleFluid, WeaklyCompressibleFluid, TruncatedLinear>;
        std::string kernel_correction = fluid_solver_config.kernel_correction_;

        if (kernel_correction == "none")
        {
            auto &complex_dynamics = main_methods.template addInteractionDynamicsOneLevel<
                AcousticHalfStepForOneBodyType, RiemannSolverType, NoKernelCorrectionCK>(inner_relation);

            addAcousticHalfStepWithSolidBodies<RiemannSolverType, NoKernelCorrectionCK>(
                sim, complex_dynamics, body_name);

            return complex_dynamics;
        }
        else
        {
            auto &complex_dynamics = main_methods.template addInteractionDynamicsOneLevel<
                AcousticHalfStepForOneBodyType, RiemannSolverType, LinearCorrectionCK>(inner_relation);

            addAcousticHalfStepWithSolidBodies<RiemannSolverType, LinearCorrectionCK>(
                sim, complex_dynamics, body_name);
            return complex_dynamics;
        }
    }

    if (sph_body.template isMatterMaterial<WeaklyCompressibleMixture>())
    {
        using RiemannSolverType =
            RiemannSolver<WeaklyCompressibleMixture, WeaklyCompressibleMixture, TruncatedLinear>;

        auto &complex_dynamics = main_methods.template addInteractionDynamicsOneLevel<
            AcousticHalfStepForOneBodyType, RiemannSolverType, LinearCorrectionCK>(inner_relation);

        addAcousticHalfStepWithSolidBodies<RiemannSolverType, LinearCorrectionCK>(
            sim, complex_dynamics, body_name);

        return complex_dynamics;
    }

    throw std::runtime_error(
        "FluidDynamicsBuilder::addAcousticHalfStepForOneBody: no supported material type found!");
}
//=================================================================================================//
template <class RiemannSolverType, class KernelCorrectionType, class AcousticHalfStepType>
void FluidDynamicsBuilder::addAcousticHalfStepWithSolidBodies(
    SPHSimulation &sim, AcousticHalfStepType &complex_dynamics, std::string body_name)
{
    auto &sph_system = sim.getSPHSystem();
    auto &config_manager = sim.getConfigManager();
    auto &solid_bodies_config = config_manager.getEntity<SPHBodiesConfig>("SolidBodiesConfig");
    for (const auto &sb_tgt : solid_bodies_config)
    {
        std::string relation_name = body_name + sb_tgt->name_;
        auto &contact_relation = sph_system.getRelationByName<
            Contact<Relation<FluidBody, SolidBody>>>(relation_name);
        complex_dynamics.template addPostContactInteraction<
            Wall, RiemannSolverType, KernelCorrectionType>(contact_relation);
    }
}
//=================================================================================================//
template <template <typename...> class InteractionMethodType, typename... PrimaryParameters,
          class FirstRelationType, typename... OtherParemeters, typename... Args>
BaseDynamics<void> &FluidDynamicsBuilder::addInteractionForOneBody(
    SPHSimulation &sim, MainMethods &main_methods, FirstRelationType &first_relation, Args &&...args)
{
    auto &main_interaction =
        main_methods.addInteractionDynamics<InteractionMethodType, PrimaryParameters...>(
            first_relation, std::forward<Args>(args)...);
    auto &fluid_identifier = first_relation.getDynamicsIdentifier();
    addInteractionWithSolidBodies<OtherParemeters...>(sim, main_interaction, fluid_identifier);
    return main_interaction;
}
//=================================================================================================//
template <typename... Parameters, class MainInteractionType, class FluidIdentifier>
void FluidDynamicsBuilder::addInteractionWithSolidBodies(
    SPHSimulation &sim, MainInteractionType &main_interaction, FluidIdentifier &fluid_identifier)
{
    auto &config_manager = sim.getConfigManager();
    auto &sph_system = sim.getSPHSystem();

    auto &solid_bodies_config = config_manager.getEntity<SPHBodiesConfig>("SolidBodiesConfig");
    for (const auto &sb_tgt : solid_bodies_config)
    {
        std::string relation_name = fluid_identifier.Name() + sb_tgt->name_;
        auto &contact_relation = sph_system.getRelationByName<
            Contact<Relation<FluidIdentifier, SolidBody>>>(relation_name);
        main_interaction.template addPostContactInteraction<Parameters...>(contact_relation);
    }
}
//=================================================================================================//
} // namespace SPH
#endif // FLUID_DYNAMICS_BUILDER_HPP
