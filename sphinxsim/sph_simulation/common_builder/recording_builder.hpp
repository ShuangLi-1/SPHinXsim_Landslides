#ifndef RECORDING_BUILDER_HPP
#define RECORDING_BUILDER_HPP

#include "recording_builder.h"

#include "sph_simulation.h"

namespace SPH
{
// SPHinXsim runs all internal dynamics in ScalingConfig's nondimensional
// units (e.g. Mass is scaled by the "Density"/"Mass" characteristic
// dimension, see base_simulation_builder.cpp jsonToReal(..., "Density")).
// The shared ReducedQuantityRecording writes whatever unit the reduce method
// produces, which is correct for plain (unscaled) SPHinXsys use, such as the
// SYCL reference, but wrong here unless converted back to physical units at
// write time - the same conversion createBodyStatesRecording and the
// observer recorder already apply via DiscreteVariable::setScalingRef.
template <class ExecutionPolicy, class LocalReduceMethodType>
class ScaledReducedQuantityRecording : public ReducedQuantityRecording<ExecutionPolicy, LocalReduceMethodType>
{
    using Base = ReducedQuantityRecording<ExecutionPolicy, LocalReduceMethodType>;
    Real physical_scaling_ref_;

  public:
    template <class DynamicsIdentifier, typename... Args>
    ScaledReducedQuantityRecording(Real physical_scaling_ref, DynamicsIdentifier &identifier, Args &&...args)
        : Base(identifier, std::forward<Args>(args)...),
          physical_scaling_ref_(physical_scaling_ref) {}

    virtual void writeToFile(size_t iteration_step = 0) override
    {
        if (!this->header_written_)
        {
            std::ofstream out_file(this->filefullpath_output_.c_str(), std::ios::out);
            out_file << "\"run_time\""
                     << "   ";
            this->plt_engine_.writeAQuantityHeader(out_file, this->reduced_quantity_, this->quantity_name_);
            out_file << "\n";
            out_file.close();
            this->header_written_ = true;
        }
        std::ofstream out_file(this->filefullpath_output_.c_str(), std::ios::app);
        out_file << this->sv_physical_time_->getValue() << "   ";
        this->reduced_quantity_ = this->reduce_method_.exec() * physical_scaling_ref_;
        this->plt_engine_.writeAQuantity(out_file, this->reduced_quantity_);
        out_file << "\n";
        out_file.close();
    }
};
//=================================================================================================//
template <class ObserverRelationType>
BaseIO *RecordingBuilder::addObserveRecorderWithVariableConfig(
    const ScalingConfig &scaling_config, const VariableConfig &variable_config,
    MainMethods &main_methods, ObserverRelationType &observer_relation)
{
    if (variable_config.type_ == "Real")
    {
        auto &ob = main_methods.template addObserveRecorder<Real>(
            observer_relation, variable_config.name_);
        ob.getObservedVariable().setScalingRef(scaling_config.getScalingRef(variable_config.name_));
        return &ob;
    }

    if (variable_config.type_ == "Vecd")
    {
        auto &ob = main_methods.template addObserveRecorder<Vecd>(
            observer_relation, variable_config.name_);
        ob.getObservedVariable().setScalingRef(scaling_config.getScalingRef(variable_config.name_));
        return &ob;
    }

    throw std::runtime_error(
        "RecordingBuilder::addObserveRecorderWithVariableConfig: no supported variable type found!");
}
//=================================================================================================//
} // namespace SPH
#endif // RECORDING_BUILDER_HPP
