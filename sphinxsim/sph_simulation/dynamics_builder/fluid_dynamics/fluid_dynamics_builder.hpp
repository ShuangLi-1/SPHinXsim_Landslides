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
    auto &fluid_body = inner_relation.getDynamicsIdentifier();
    std::string body_name = fluid_body.Name();
    auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");

    if (fluid_body.template isMatterMaterial<WeaklyCompressibleFluid>())
    {
        using RiemannSolverType =
            RiemannSolver<WeaklyCompressibleFluid, WeaklyCompressibleFluid, TruncatedLinear>;
        std::string kernel_correction = fluid_solver_config.kernel_correction_;

        if (kernel_correction == "none")
        {
            auto &complex_dynamics = main_methods.template addInteractionDynamicsOneLevel<
                AcousticHalfStepForOneBodyType, RiemannSolverType, NoKernelCorrectionCK>(inner_relation);

            addInteractionWithSolidBodies<Wall, RiemannSolverType, NoKernelCorrectionCK>(
                sim, complex_dynamics, fluid_body);

            return complex_dynamics;
        }
        else
        {
            auto &complex_dynamics = main_methods.template addInteractionDynamicsOneLevel<
                AcousticHalfStepForOneBodyType, RiemannSolverType, LinearCorrectionCK>(inner_relation);

            addInteractionWithSolidBodies<Wall, RiemannSolverType, LinearCorrectionCK>(
                sim, complex_dynamics, fluid_body);
            return complex_dynamics;
        }
    }

    if (fluid_body.template isMatterMaterial<WeaklyCompressibleMixture>())
    {
        using RiemannSolverType =
            RiemannSolver<WeaklyCompressibleMixture, WeaklyCompressibleMixture, TruncatedLinear>;

        auto &complex_dynamics = main_methods.template addInteractionDynamicsOneLevel<
            AcousticHalfStepForOneBodyType, RiemannSolverType, LinearCorrectionCK>(inner_relation);

        addInteractionWithSolidBodies<Wall, RiemannSolverType, LinearCorrectionCK>(
            sim, complex_dynamics, fluid_body);

        return complex_dynamics;
    }

    throw std::runtime_error(
        "FluidDynamicsBuilder::addAcousticHalfStepForOneBody: no supported material type found!");
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
