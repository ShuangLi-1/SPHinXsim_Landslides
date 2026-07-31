#ifndef FLUID_DYNAMICS_BUILDER_HPP
#define FLUID_DYNAMICS_BUILDER_HPP

#include "fluid_boundary_builder.hpp"
#include "fluid_dynamics_builder.h"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
using namespace fluid_dynamics;
//=================================================================================================//
template <class FluidType, class MethodContainerType, class InnerRelationType, class ContactRelationType>
BaseDynamics<void> &FluidDynamicsBuilder::buildDensityRegularization(
    SPHSimulation &sim, MethodContainerType &method_container, InnerRelationType &inner_relation,
    ContactRelationType &contact_relation, const std::string &surface_type)
{
    auto &density_summation =
        method_container.template addInteractionDynamics<CompressionSummation>(inner_relation)
            .addPostContactInteraction(contact_relation);

    auto &initialization_pipeline = sim.getInitializationPipeline();
    SPHBody &sph_body = inner_relation.getSPHBody();

    auto &average_compression = method_container.template addReduceDynamics<AverageCompression>(sph_body);
    initialization_pipeline.insert_hook(
        InitializationHookPoint::InitialCondition, [&]()
        { 
            density_summation.exec();
            Real average_compression_value = average_compression.exec();
            std::cout << "\n------------------------------------------------------------" << std::endl;
            std::cout << "FluidDynamicsBuilder::buildDensityRegularization : " 
                      << "Initial average compression of FluidBody '" << sph_body.Name() 
                      << "' is " << average_compression_value << std::endl; 
            std::cout << "------------------------------------------------------------" << std::endl; });

    auto &minimum_compression =
        method_container.template addReduceDynamics<QuantityReduce, ReduceMin<Real>>(sph_body, "Compression");
    auto &maximum_compression =
        method_container.template addReduceDynamics<QuantityReduce, ReduceMax<Real>>(sph_body, "Compression");
    initialization_pipeline.insert_hook(
        InitializationHookPoint::PreSimulationSanityCheck, [&]()
        {
            Real lower_limit = minimum_compression.exec();
            Real upper_limit = maximum_compression.exec();
            if (lower_limit < 0.95 || upper_limit > 1.05)
            {
                std::cout << "\n------------------------------------------------------------" << std::endl;
                std::cout << "Error: Compression is out of range!" << std::endl;
                std::cout << "Lower limit: " << lower_limit << " Upper limit: "<< upper_limit << std::endl;
                std::cout << "The possible issues are the following:" << std::endl;
                std::cout << "- Too large: overlapped bodies" << std::endl;
                std::cout << "- Too small: insufficient resolution due to thin layer" << std::endl;
                std::cout << "------------------------------------------------------------" << std::endl;
            } });

    auto &density_regularization = method_container.addParticleDynamicsGroup();
    density_regularization.add(&density_summation);

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

    if (surface_type == "free_stream")
    {
        density_regularization.add(
            &method_container.template addStateDynamics<
                DensityRegularization, FluidType, FreeStream>(sph_body));
        return density_regularization;
    }

    throw std::runtime_error(
        "FluidDynamicsBuilder::buildDensityRegularization: no supported surface type found!");
}
//=================================================================================================//
} // namespace SPH
#endif // FLUID_DYNAMICS_BUILDER_HPP
