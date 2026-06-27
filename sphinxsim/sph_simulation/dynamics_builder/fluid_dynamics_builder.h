/* ------------------------------------------------------------------------- *
 *                                SPHinXsys                                  *
 * ------------------------------------------------------------------------- *
 * SPHinXsys (pronunciation: s'finksis) is an acronym from Smoothed Particle *
 * Hydrodynamics for industrial compleX systems. It provides C++ APIs for    *
 * physical accurate simulation and aims to model coupled industrial dynamic *
 * systems including fluid, solid, multi-body dynamics and beyond with SPH   *
 * (smoothed particle hydrodynamics), a meshless computational method using  *
 * particle discretization.                                                  *
 *                                                                           *
 * SPHinXsys is partially funded by German Research Foundation               *
 * (Deutsche Forschungsgemeinschaft) DFG HU1527/6-1, HU1527/10-1,            *
 *  HU1527/12-1 and HU1527/12-4.                                             *
 *                                                                           *
 * Portions copyright (c) 2017-2025 Technical University of Munich and       *
 * the authors' affiliations.                                                *
 *                                                                           *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may   *
 * not use this file except in compliance with the License. You may obtain a *
 * copy of the License at http://www.apache.org/licenses/LICENSE-2.0.        *
 *                                                                           *
 * ------------------------------------------------------------------------- */
/**
 * @file    fluid_dynamics_builder.h
 * @brief   Shared builders for fluid-like auxiliary dynamics.
 * @author  Xiangyu Hu
 */

#ifndef FLUID_DYNAMICS_BUILDER_H
#define FLUID_DYNAMICS_BUILDER_H

#include "base_simulation_builder.h"

namespace SPH
{
class FluidDynamicsBuilder
{
  public:
    template <class FluidType, class MethodContainerType, class InnerRelationType, class ContactRelationType>
    static BaseDynamics<void> &buildDensityRegularization(
        MethodContainerType &method_container, InnerRelationType &inner_relation,
        ContactRelationType &contact_relation, const std::string &surface_type);

  private:
    template <class MethodContainerType, class InnerRelationType, class ContactRelationType>
    static decltype(auto) addDensitySummation(
        MethodContainerType &method_container, InnerRelationType &inner_relation,
        ContactRelationType &contact_relation);

    template <class FluidType, class FlowType, class... ParticleScopes, class CompressionSummationType>
    static BaseDynamics<void> &addDensityRegularization(
        CompressionSummationType &compression_summation, SPHBody &sph_body);
};
} // namespace SPH
#endif // FLUID_DYNAMICS_BUILDER_H
