#include "sph_simulation.h"

#include "continuum_simulation_builder.h"
#include "fluid_simulation_builder.h"
#include "geometry_builder.h"
#include "material_builder.h"
#include "particle_generation.h"
#include "recording_builder.h"

namespace SPH
{
//=================================================================================================//
SPHSimulation::SPHSimulation(const fs::path &config_path)
    : config_path_(config_path), recording_builder_ptr_(std::make_unique<RecordingBuilder>())
{
    IO::initEnvironment();
}
//=================================================================================================//
SPHSimulation::~SPHSimulation() = default;
//=================================================================================================//
void SPHSimulation::resetOutputRoot(const fs::path &output_root, bool keep_existing)
{
    IOEnvironment &io_env = IO::getEnvironment();
    if (!fs::exists(output_root))
    {
        fs::create_directories(output_root);
    }
    io_env.resetOutputFolder((output_root / "output").string(), keep_existing);
    io_env.resetRestartFolder((output_root / "restart").string(), keep_existing);
    io_env.resetReloadFolder((output_root / "reload").string(), keep_existing);
}
//=================================================================================================//
SPHSystem &SPHSimulation::defineSPHSystem()
{
    SystemDomainConfig &system_config = config_manager_.getEntity<
        SystemDomainConfig>("SystemDomainConfig");
    sph_system_ptr_ = std::make_unique<SPHSystem>(
        system_config.system_bounds_, system_config.particle_spacing_);
    auto &scaling_config = config_manager_.getEntity<ScalingConfig>("ScalingConfig");
    sph_system_ptr_->svPhysicalTime().setScalingRef(scaling_config.getScalingRef("Time"));
    sph_system_ptr_->writeSystemDomainShapeToVtp(scaling_config.getScalingRef("Length"));
    return *sph_system_ptr_.get();
}
//=================================================================================================//
SPHSolver &SPHSimulation::defineSPHSolver(SimulationBuilder &simulation_builder, const json &config)
{
    simulation_builder.parseSolverParameters(config_manager_, config.at("solver_parameters"));
    sph_solver_ptr_ = std::make_unique<SPHSolver>(getSPHSystem());
    return *sph_solver_ptr_.get();
}
//=================================================================================================//
StagePipeline<InitializationHookPoint> &SPHSimulation::getInitializationPipeline()
{
    return initialization_pipeline_;
}
//=================================================================================================//
StagePipeline<SimulationHookPoint> &SPHSimulation::getSimulationPipeline()
{
    return simulation_pipeline_;
}
//=================================================================================================//
EntityManager &SPHSimulation::getConfigManager()
{
    return config_manager_;
}
//=================================================================================================//
void SPHSimulation::generateParticles()
{
    if (!geometry_built_)
    {
        std::cerr << "SPHSimulation::generateParticles: Geometries are not built. "
                     "Call buildGeometries() before generateParticles().\n";
        exit(1);
    }

    json config = loadConfig().at("particle_generation");
    if (config.at("build_and_run").get<bool>())
    {
        particle_generation_ptr_ = std::make_unique<ParticleGeneration>();
        particle_generation_ptr_->buildParticleGeneration(*this, config.at("settings"));
        particle_generation_ptr_->runRelaxation();
        particles_generated_ = true;
        geometry_locked_ = true;
    }
}
//=================================================================================================//
void SPHSimulation::buildGeometries()
{
    if (geometry_locked_)
    {
        throw std::runtime_error(
            "SPHSimulation::buildGeometries: geometry is locked after particle generation. "
            "Call resetAfterGeometryChange() before modifying geometry.");
    }

    json config = loadConfig();
    config_manager_.clear();
    config_manager_.emplaceEntity<ScalingConfig>("ScalingConfig", config);
    GeometryBuilder::createGeometries(config_manager_, config.at("geometries"));
    geometry_built_ = true;
    executable_simulation_state_ready_ = false;
}
//=================================================================================================//
void SPHSimulation::resetAfterGeometryChange()
{
    particle_generation_ptr_.reset();
    sph_system_ptr_.reset();
    sph_solver_ptr_.reset();
    initialization_pipeline_ = StagePipeline<InitializationHookPoint>();
    simulation_pipeline_ = StagePipeline<SimulationHookPoint>();
    executable_simulation_state_ready_ = false;
    particles_generated_ = false;
    geometry_locked_ = false;
}
//=================================================================================================//
bool SPHSimulation::isGeometryLocked() const
{
    return geometry_locked_;
}
//=================================================================================================//
bool SPHSimulation::hasBuiltGeometries() const
{
    return geometry_built_;
}
//=================================================================================================//
bool SPHSimulation::hasGeneratedParticles() const
{
    return particles_generated_;
}
//=================================================================================================//
std::map<std::string, std::pair<std::vector<double>, std::vector<double>>> SPHSimulation::getShapeBounds()
{
    std::map<std::string, std::pair<std::vector<double>, std::vector<double>>> result;
    for (Shape *shape : config_manager_.entitiesWith<Shape>())
    {
        BoundingBoxd bounds = shape->getBounds();
        std::vector<double> lower(bounds.lower_.data(), bounds.lower_.data() + bounds.lower_.size());
        std::vector<double> upper(bounds.upper_.data(), bounds.upper_.data() + bounds.upper_.size());
        result[shape->Name()] = {lower, upper};
    }
    return result;
}
//=================================================================================================//
void SPHSimulation::buildSimulation()
{
    if (!particle_generation_ptr_)
    {
        std::cerr << "SPHSimulation::buildSimulation: ParticleGeneration not found. "
                     "Call createParticlesGeneration() before buildSimulation().\n";
        exit(1);
    }

    json config = loadConfig();
    if (config.contains("simulation_type"))
    {
        std::string simulation_type = config.at("simulation_type").get<std::string>();

        if (simulation_type == "fluid_dynamics")
        {
            FluidSimulationBuilder fluid_simulation_builder;
            fluid_simulation_builder.buildSimulation(*this, config);
            return;
        }

        if (simulation_type == "continuum_dynamics")
        {
            ContinuumSimulationBuilder continuum_simulation_builder;
            continuum_simulation_builder.buildSimulation(*this, config);
            return;
        }

        throw std::runtime_error(
            "SPHSimulation::buildSimulationFromJson: unsupported simulation type: " + simulation_type);
    }
}
//=================================================================================================//
json SPHSimulation::loadConfig()
{
    json config;
    std::ifstream file(config_path_);
    if (!file.is_open())
    {
        throw std::runtime_error(
            "SPHSimulation::loadConfig: unable to open config file " + config_path_.string());
    }
    file >> config;
    return config;
}
//=================================================================================================//
void SPHSimulation::initializeSimulation()
{
    if (!sph_solver_ptr_)
    {
        throw std::runtime_error(
            "SPHSimulation::initializeSimulation: simulation is not built. "
            "Call buildSimulation() first.");
    }

    for (auto &step : initialization_pipeline_.main_steps)
    {
        step(); // each step touches all cells internally
    }

    executable_simulation_state_ready_ = true;
}
//=================================================================================================//
void SPHSimulation::run()
{
    SolverCommonConfig &solver_common_config =
        config_manager_.getEntity<SolverCommonConfig>("SolverCommonConfig");

    stepTo(solver_common_config.end_time_);
}
//=================================================================================================//
void SPHSimulation::stepTo(Real target_time)
{
    if (!executable_simulation_state_ready_)
    {
        std::cerr << "SPHSimulation::run: Simulation is not initialized. "
                     "Call initializeSimulation() before run.\n";
        return;
    }

    TimeStepper &time_stepper = sph_solver_ptr_->getTimeStepper();
    while (!time_stepper.isEndTime(target_time))
    {
        for (auto &step : simulation_pipeline_.main_steps)
        {
            step(); // each step touches all cells internally
        }
    }
}
//=================================================================================================//
void SPHSimulation::stepBy(Real interval)
{
    TimeStepper &time_stepper = sph_solver_ptr_->getTimeStepper();
    Real present_time_ = time_stepper.getPhysicalTime();
    stepTo(present_time_ + interval);
}
//=================================================================================================//
void SPHSimulation::rerunParticleRelaxation()
{
    if (!particles_generated_ || !particle_generation_ptr_)
    {
        std::cerr << "SPHSimulation::rerunParticleGeneration: ParticleGeneration not found. "
                     "Call createParticlesGeneration() before rerunParticleGeneration\n";

        exit(1);
    }
    particle_generation_ptr_->runRelaxation();
}
//=================================================================================================//
} // namespace SPH
