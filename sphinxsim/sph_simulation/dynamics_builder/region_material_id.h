/**
 * @file    region_material_id.h
 * @brief   Assigns a per-particle material id from a polynomial region model.
 *          A polynomial envelope, evaluated about a given center, splits the
 *          body into an outer region (id 0), a core/tip region (id 2) and the
 *          remainder (id 1). All shape values come from the configuration, so
 *          the same dynamics serves any body described this way.
 * @author  Pruthvik Arasikere Mallikarjuna and Xiangyu Hu
 */

#ifndef REGION_MATERIAL_ID_H
#define REGION_MATERIAL_ID_H

#include "base_local_dynamics.h"
#include "complex_solid.h"

namespace SPH
{
class PolynomialRegionMaterialId : public MaterialIdInitialization
{
  public:
    PolynomialRegionMaterialId(SPHBody &sph_body, const StdVec<Real> &coefficients,
                               Vecd center, Real region_span, Real tip_span,
                               Real core_thickness, Real envelope_offset)
        : MaterialIdInitialization(sph_body),
          dv_material_id_(particles_->getVariableByName<int>("MaterialID")),
          dv_pos_(particles_->getVariableByName<Vecd>("Position")),
          center_(center), region_span_(region_span), tip_span_(tip_span),
          core_thickness_(core_thickness), envelope_offset_(envelope_offset)
    {
        // The envelope is a fifth order polynomial without a constant term, so exactly five coefficients are expected.
        if (coefficients.size() != 5)
        {
            throw std::runtime_error(
                "PolynomialRegionMaterialId: expected five envelope coefficients.");
        }
        for (size_t k = 0; k != 5; ++k)
        {
            a_[k] = coefficients[k];
        }
    }

    class UpdateKernel
    {
      public:
        template <typename ExecutionPolicy>
        UpdateKernel(const ExecutionPolicy &ex_policy, PolynomialRegionMaterialId &encloser)
            : material_id_(encloser.dv_material_id_->DelegatedData(ex_policy)),
              pos_(encloser.dv_pos_->DelegatedData(ex_policy)),
              center_(encloser.center_), region_span_(encloser.region_span_),
              tip_span_(encloser.tip_span_), core_thickness_(encloser.core_thickness_),
              envelope_offset_(encloser.envelope_offset_)
        {
            for (size_t k = 0; k != 5; ++k)
            {
                a_[k] = encloser.a_[k];
            }
        }

        void update(size_t index_i, Real dt = 0.0)
        {
            Real x = pos_[index_i][0] - center_[0];
            Real y = pos_[index_i][1];
            Real cy = center_[1];
            Real half_core = core_thickness_ / 2;

            // Envelope height at this station, measured from the mid line.
            Real y1 = a_[0] * math::pow(x, Real(1)) + a_[1] * math::pow(x, Real(2)) +
                      a_[2] * math::pow(x, Real(3)) + a_[3] * math::pow(x, Real(4)) +
                      a_[4] * math::pow(x, Real(5));

            // Outside the envelope and clear of the core: outer region.
            if (x <= (region_span_ - tip_span_) && y > (y1 - envelope_offset_ + cy) && y > (cy + half_core))
            {
                material_id_[index_i] = 0;
            }
            else if (x <= (region_span_ - tip_span_) && y < (-y1 + envelope_offset_ + cy) && y < (cy - half_core))
            {
                material_id_[index_i] = 0;
            }
            // The tip station, or the band straddling the mid line: core region.
            else if ((x > (region_span_ - tip_span_)) || ((y < (cy + half_core)) && (y > (cy - half_core))))
            {
                material_id_[index_i] = 2;
            }
            // Everything in between.
            else
            {
                material_id_[index_i] = 1;
            }
        }

      protected:
        int *material_id_;
        Vecd *pos_;
        Vecd center_;
        Real region_span_, tip_span_, core_thickness_, envelope_offset_;
        Real a_[5];
    };

  protected:
    DiscreteVariable<int> *dv_material_id_;
    DiscreteVariable<Vecd> *dv_pos_;
    Vecd center_;
    Real region_span_, tip_span_, core_thickness_, envelope_offset_;
    Real a_[5];
};
} // namespace SPH

#endif // REGION_MATERIAL_ID_H