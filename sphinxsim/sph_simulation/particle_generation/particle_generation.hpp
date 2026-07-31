#ifndef PARTICLE_GENERATION_HPP
#define PARTICLE_GENERATION_HPP

#include "particle_generation.h"

#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
template <class OrientedBoxPartType, class ConstraintMethodType>
class OrientedBoxConstraint : public BaseLocalDynamics<OrientedBoxPartType>
{
    using DataType = typename ConstraintMethodType::ReturnType;

  public:
    template <typename... Args>
    OrientedBoxConstraint(OrientedBoxPartType &oriented_box_part, const std::string &variable_name, Args &&...args)
        : BaseLocalDynamics<OrientedBoxPartType>(oriented_box_part),
          sv_oriented_box_(oriented_box_part.svOrientedBox()),
          dv_variable_(this->particles_->template getVariableByName<DataType>(variable_name)),
          constraint_(std::forward<Args>(args)...){};

    class UpdateKernel
    {
      public:
        template <class ExecutionPolicy, class EncloserType>
        UpdateKernel(const ExecutionPolicy &ex_policy, EncloserType &encloser)
            : oriented_box_(encloser.sv_oriented_box_->DelegatedData(ex_policy)),
              variable_(encloser.dv_variable_->DelegatedData(ex_policy)),
              constraint_(encloser.constraint_){};

        void update(size_t index_i, Real dt = 0.0)
        {
            variable_[index_i] = constraint_(oriented_box_->getTransform(), variable_[index_i]);
        };

      protected:
        OrientedBox *oriented_box_;
        DataType *variable_;
        ConstraintMethodType constraint_;
    };

  protected:
    SingleVariable<OrientedBox> *sv_oriented_box_;
    DiscreteVariable<DataType> *dv_variable_;
    ConstraintMethodType constraint_;
};

class CovariantVectorAxis : public ReturnFunction<Vecd>
{
    Vecd constraint_value_;
    int axis_;

  public:
    CovariantVectorAxis(int axis) : constraint_value_(Vecd::Zero()), axis_(axis) {};

    Vecd operator()(const Transform &transform, const Vecd &variable)
    {
        Vecd frame_variable = transform.xformBaseVecToFrame(variable);
        frame_variable[axis_] = constraint_value_[axis_];
        return transform.xformFrameVecToBase(frame_variable);
    };
};
//=================================================================================================//
} // namespace SPH
#endif // PARTICLE_GENERATION_HPP
