/**
 * @file    composite_solid.h
 * @brief   Three-region composite elastic solid: one active-strain region and
 *          two Saint-Venant regions, selected per particle by MaterialID.
 * @author  Pruthvik Arasikere Mallikarjuna and Xiangyu Hu
 */

#ifndef COMPOSITE_SOLID_H
#define COMPOSITE_SOLID_H

#include "active_model.h"
#include "complex_solid.h"
#include "elastic_solid.h"

namespace SPH
{
class CompositeSolidMaterial : public CompositeSolid
{
  public:
    CompositeSolidMaterial(Real rho0, Real youngs_modulus_active,
                           Real youngs_modulus_1, Real youngs_modulus_2, Real poisson)
        : CompositeSolid(rho0)
    {
        add<ActiveModelSolid>(rho0, youngs_modulus_active, poisson);
        add<SaintVenantKirchhoffSolid>(rho0, youngs_modulus_1, poisson);
        add<SaintVenantKirchhoffSolid>(rho0, youngs_modulus_2, poisson);
    }

    virtual void initializeLocalParameters(BaseParticles *base_particles) override
    {
        CompositeSolid::initializeLocalParameters(base_particles);
        dv_material_id_ = base_particles->getVariableByName<int>("MaterialID");
    }

    class ConstituteKernel
    {
      public:
        template <typename ExecutionPolicy>
        ConstituteKernel(const ExecutionPolicy &ex_policy, CompositeSolidMaterial &encloser)
            : material_id_(encloser.dv_material_id_->DelegatedData(ex_policy)),
              active_kernel_(ex_policy, static_cast<ActiveModelSolid &>(*encloser.composite_materials_[0])),
              svk1_kernel_(ex_policy, static_cast<SaintVenantKirchhoffSolid &>(*encloser.composite_materials_[1])),
              svk2_kernel_(ex_policy, static_cast<SaintVenantKirchhoffSolid &>(*encloser.composite_materials_[2])) {}

        inline Matd StressPK1(const Matd &F, size_t index_i)
        {
            if (material_id_[index_i] == 0)
                return active_kernel_.StressPK1(F, index_i);
            else if (material_id_[index_i] == 1)
                return svk1_kernel_.StressPK1(F, index_i);
            else
                return svk2_kernel_.StressPK1(F, index_i);
        }

        inline Real VolumetricKirchhoff(Real J) { return 0.0; }

        inline Real PairNumericalDamping(Real dE_dt_ij, Real smoothing_length)
        {
            return active_kernel_.PairNumericalDamping(dE_dt_ij, smoothing_length);
        }

      protected:
        int *material_id_;
        ActiveModelSolid::ConstituteKernel active_kernel_;
        SaintVenantKirchhoffSolid::ConstituteKernel svk1_kernel_;
        SaintVenantKirchhoffSolid::ConstituteKernel svk2_kernel_;
    };

  protected:
    DiscreteVariable<int> *dv_material_id_;
};
} // namespace SPH

#endif // COMPOSITE_SOLID_H