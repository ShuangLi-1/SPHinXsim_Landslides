#include "recording_builder.h"

#include "sph_simulation.h"

namespace SPH
{
//=================================================================================================//
std::string RecordingBuilder::getObserverRelationName(const ObserverConfig &observer_config)
{
    return observer_config.name_ + observer_config.observed_body_;
}
//=================================================================================================//
ObserverConfig RecordingBuilder::parseObserverConfig(const json &config)
{
    ObserverConfig observer_config;
    observer_config.name_ = config.at("name").get<std::string>();
    observer_config.observed_body_ = config.at("observed_body").get<std::string>();
    observer_config.observed_variable_ = parseVariableConfig(config.at("variable"));
    return observer_config;
}
//=================================================================================================//
void RecordingBuilder::addObserves(
    SPHSystem &sph_system, EntityManager &config_manager, const json &config)
{
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    for (const auto &ob : config)
    {
        ObserverConfig observer_config = parseObserverConfig(ob);
        std::string name = observer_config.name_;
        config_manager.emplaceEntity<ObserverConfig>(name, observer_config);

        StdVec<Vecd> positions;
        if (ob.contains("positions"))
        {
            for (const auto &p : ob.at("positions"))
            {
                positions.push_back(scaling_config.jsonToVecd(p, "Length"));
            }
        }

        ObserverBody &observer_body = sph_system.addBody<ObserverBody>(name);
        observer_body.generateParticles<ObserverParticles>(positions);
    }
}
//=================================================================================================//
void RecordingBuilder::addVariableToStateRecorder(
    BodyStatesRecording &state_recording, SPHBody &sph_body, const json &config)
{
    for (const auto &[type_key, _] : config.items())
    {
        if (type_key != "int_type" && type_key != "real_type" && type_key != "vector_type")
        {
            throw std::runtime_error(
                "RecordingBuilder::addVariableToStateRecorder unsupported variable type key: " +
                type_key + ". Supported keys are: int_type, real_type, vector_type.");
        }
    }

    if (config.contains("int_type"))
    {
        StdVec<std::string> int_variables = config.at("int_type").get<StdVec<std::string>>();
        for (const auto &int_var : int_variables)
        {
            state_recording.template addToWrite<int>(sph_body, int_var);
        }
    }

    if (config.contains("real_type"))
    {
        StdVec<std::string> real_variables = config.at("real_type").get<StdVec<std::string>>();
        for (const auto &real_var : real_variables)
        {
            state_recording.template addToWrite<Real>(sph_body, real_var);
        }
    }

    if (config.contains("vector_type"))
    {
        StdVec<std::string> vector_variables = config.at("vector_type").get<StdVec<std::string>>();
        for (const auto &vector_var : vector_variables)
        {
            state_recording.template addToWrite<Vecd>(sph_body, vector_var);
        }
    }
}
//=================================================================================================//
} // namespace SPH
