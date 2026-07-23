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
 * @file    solid_dynamics_builder.hpp
 * @brief   Builds the elastic solid stress relaxation group and drives it
 *          as a sub loop inside each coupling interval.
 * @author  Pruthvik Arasikere Mallikarjuna and Xiangyu Hu
 */

#ifndef SOLID_DYNAMICS_BUILDER_HPP
#define SOLID_DYNAMICS_BUILDER_HPP

#include "solid_dynamics_builder.h"

#include "material_builder.h"
#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class MaterialType, class MethodContainerType, class InnerRelationType>
auto &SolidDynamicsBuilder::buildSolidDynamics(
    SPHSimulation &sim, MethodContainerType &method_container,
    InnerRelationType &inner_relation)
{
    auto &sph_system = sim.getSPHSystem();
    auto &time_stepper = sim.getSPHSolver().getTimeStepper();

    std::string body_name = inner_relation.getSPHBody().Name();
    RealBody &real_body = sph_system.getBodyByName<RealBody>(body_name);

    // Solid stress relaxation reads these kinematic variables; register them
    // before the stress steps so they exist when the steps are constructed
    BaseParticles &solid_particles = real_body.getBaseParticles();
    solid_particles.registerStateVariable<Vecd>("Velocity");
    solid_particles.registerStateVariable<Vecd>("Force");
    solid_particles.registerStateVariable<Vecd>("ForcePrior");
    solid_particles.addEvolvingVariable<Vecd>("Velocity");

    auto &correction_matrix =
    method_container.template addInteractionDynamics<LinearCorrectionMatrix, WithUpdate>(inner_relation);

    // the solid picks its own step from the wave speed; this drives the sub-loop
    auto &solid_time_step =
        method_container.template addReduceDynamics<solid_dynamics::AcousticTimeStepCK>(real_body);

    // stress relaxation runs as damping, then the two PK2 half steps, in this order
    auto &numerical_damping =
        method_container.template addInteractionDynamicsWithUpdate<
            solid_dynamics::StructureNumericalDamping, MaterialType>(inner_relation);
    auto &stress_first_half =
        method_container.template addInteractionDynamicsOneLevel<
            solid_dynamics::StructureIntegration1stHalfPK2, MaterialType>(inner_relation);
    auto &stress_second_half =
        method_container.template addInteractionDynamicsOneLevel<
            solid_dynamics::StructureIntegration2ndHalf>(inner_relation);

    auto &solid_relaxation = method_container.addParticleDynamicsGroup();
    solid_relaxation.add(&numerical_damping).add(&stress_first_half).add(&stress_second_half);

    // fill each coupling interval with as many solid sub-steps as it takes
    auto &simulation_pipeline = sim.getSimulationPipeline();
    simulation_pipeline.insert_hook(
        SimulationHookPoint::CouplingSynchronization, [&]()
        {
          Real dt = time_stepper.getGlobalTimeStepSize();
          if (!(dt > 0.0))
          {
              throw std::runtime_error(
                  "SolidDynamicsBuilder: coupling interval is not a positive number, the solid state is degenerate.");
          }
          time_stepper.integrateMatchedTimeInterval(solid_relaxation, dt, solid_time_step); 
        });
    return correction_matrix;
}
//=================================================================================================//
} // namespace SPH
#endif // SOLID_DYNAMICS_BUILDER_HPP