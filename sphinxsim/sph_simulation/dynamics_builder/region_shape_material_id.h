/**
 * @file    region_shape_material_id.h
 * @brief   Assigns a per particle material id from a list of region shapes.
 *          Containment is resolved on the host at construction, since a shape
 *          query is a host side operation, and the result is written into the
 *          MaterialID variable. Regions, their ids and the default come from
 *          the configuration, so any body described this way can be split.
 * @author  Pruthvik Arasikere Mallikarjuna and Xiangyu Hu
 */

#ifndef REGION_SHAPE_MATERIAL_ID_H
#define REGION_SHAPE_MATERIAL_ID_H

#include "base_local_dynamics.h"
#include "complex_solid.h"

namespace SPH
{
class RegionShapeMaterialId : public MaterialIdInitialization
{
  public:
    RegionShapeMaterialId(SPHBody &sph_body, StdVec<Shape *> region_shapes,
                          StdVec<int> region_ids, int default_id)
        : MaterialIdInitialization(sph_body),
          dv_material_id_(particles_->getVariableByName<int>("MaterialID")),
          dv_pos_(particles_->getVariableByName<Vecd>("Position"))
    {
        if (region_shapes.size() != region_ids.size())
        {
            throw std::runtime_error(
                "RegionShapeMaterialId: number of region shapes and ids must match.");
        }
        // Resolve the id of every particle now, on the host, using the shape
        // containment query. The first region that contains a particle wins.
        Vecd *pos = dv_pos_->Data();
        int *material_id = dv_material_id_->Data();
        for (size_t index_i = 0; index_i != particles_->TotalRealParticles(); ++index_i)
        {
            int assigned = default_id;
            for (size_t r = 0; r != region_shapes.size(); ++r)
            {
                if (region_shapes[r]->checkContain(pos[index_i]))
                {
                    assigned = region_ids[r];
                    break;
                }
            }
            material_id[index_i] = assigned;
        }
    }

    // Nothing to do per element: the ids were assigned in the constructor.
    struct UpdateKernel
    {
        template <typename ExecutionPolicy>
        UpdateKernel(const ExecutionPolicy &ex_policy, RegionShapeMaterialId &encloser) {}
        void update(size_t index_i, Real dt = 0.0) {}
    };

  protected:
    DiscreteVariable<int> *dv_material_id_;
    DiscreteVariable<Vecd> *dv_pos_;
};
} // namespace SPH

#endif // REGION_SHAPE_MATERIAL_ID_H
