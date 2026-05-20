#include "material_builder.h"

#include "fluid_simulation_builder.h"
#include "sphinxsys.h"

namespace SPH
{
//=================================================================================================//
void MaterialBuilder::addMaterial(EntityManager &config_manager, SPHBody &sph_body, const json &config)
{
    addMatterMaterial(config_manager, sph_body, config);
    addOtherMaterialProperties(config_manager, sph_body, config);
}
//=================================================================================================//
void MaterialBuilder::addMatterMaterial(
    EntityManager &config_manager, SPHBody &sph_body, const json &config)
{
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    const std::string type = config.at("type").get<std::string>();

    if (type == "weakly_compressible_fluid")
    {
        Real density = scaling_config.jsonToReal(config.at("density"), "Density");
        auto &fluid_solver_config = config_manager.getEntity<FluidSolverConfig>("FluidSolverConfig");
        Real u_max_factor = fluid_solver_config.max_velocity_factor_;
        Real sound_speed = 10.0 * u_max_factor; // 10 times of the maximum anticipated velocity
        auto &material = sph_body.defineMatterMaterial<WeaklyCompressibleFluid>(density, sound_speed);
        config_manager.addEntity(sph_body.Name() + "WeaklyCompressibleFluid", &material);
        return;
    }

    if (type == "rigid_body")
    {
        auto &material = sph_body.defineMatterMaterial<Solid>();
        config_manager.addEntity(sph_body.Name() + "RigidBody", &material);
        return;
    }

    if (type == "j2_plasticity")
    {
        Real density = scaling_config.jsonToReal(config.at("density"), "Density");
        Real sound_speed = scaling_config.jsonToReal(config.at("sound_speed"), "Speed");
        Real youngs_modulus = scaling_config.jsonToReal(config.at("youngs_modulus"), "Stress");
        Real poisson_ratio = scaling_config.jsonToReal(config.at("poisson_ratio"), "Dimensionless");
        Real yield_stress = scaling_config.jsonToReal(config.at("yield_stress"), "Stress");
        Real hardening_modulus = scaling_config.jsonToReal(config.at("hardening_modulus"), "Stress");
        auto &material = sph_body.defineMatterMaterial<J2Plasticity>(
            density, sound_speed, youngs_modulus, poisson_ratio, yield_stress, hardening_modulus);
        config_manager.addEntity(sph_body.Name() + "J2Plasticity", &material);
        return;
    }

    if (type == "general_continuum")
    {
        Real density = scaling_config.jsonToReal(config.at("density"), "Density");
        Real sound_speed = scaling_config.jsonToReal(config.at("sound_speed"), "Speed");
        Real youngs_modulus = scaling_config.jsonToReal(config.at("youngs_modulus"), "Stress");
        Real poisson_ratio = scaling_config.jsonToReal(config.at("poisson_ratio"), "Dimensionless");
        auto &material = sph_body.defineMatterMaterial<GeneralContinuum>(
            density, sound_speed, youngs_modulus, poisson_ratio);
        config_manager.addEntity(sph_body.Name() + "GeneralContinuum", &material);
        return;
    }

    throw std::runtime_error("MaterialBuilder::addMatterMaterial: unsupported material: " + type);
}
//=================================================================================================//
void MaterialBuilder::addOtherMaterialProperties(
    EntityManager &config_manager, SPHBody &sph_body, const json &config)
{
    if (config.contains("viscosity"))
    {
        addViscosity(config_manager, sph_body, config.at("viscosity"));
    }

    if (config.contains("thermal_properties"))
    {
        addThermalProperties(config_manager, sph_body, config.at("thermal_properties"));
    }
}
//=================================================================================================//
void MaterialBuilder::addViscosity(EntityManager &config_manager, SPHBody &sph_body, const json &config)
{
    Real mu_ref = 0.0;
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");

    if (config.contains("Reynolds_number"))
    {
        mu_ref = 1.0 / scaling_config.jsonToReal(config.at("Reynolds_number"), "Dimensionless");
    }
    else
    {
        mu_ref = scaling_config.jsonToReal(config, "Viscosity");
    }
    sph_body.addMaterialProperty<Viscosity>(mu_ref);
}
//=================================================================================================//
void MaterialBuilder::addThermalProperties(
    EntityManager &config_manager, SPHBody &sph_body, const json &config)
{
    auto &scaling_config = config_manager.getEntity<ScalingConfig>("ScalingConfig");
    if (!config.contains("thermal_boundary"))
    {
        Real d_coeff_ref = scaling_config.jsonToReal(
            config.at("thermal_conductivity"), "ThermalConductivity");
        Real cv = scaling_config.jsonToReal(
            config.at("volumetric_heat_capacity"), "VolumetricHeatCapacity");

        sph_body.addMaterialProperty<IsotropicDiffusion>("Temperature", "Temperature", d_coeff_ref, cv);
        return;
    }
    else
    {
        ThermalBoundaryConfig boundary_config = parseThermalBoundaryConfig(config.at("thermal_boundary"));
        config_manager.emplaceEntity<ThermalBoundaryConfig>(sph_body.Name(), boundary_config);
        return;
    }
    throw std::runtime_error(
        "MaterialBuilder::addThermalProperties: unsupported thermal property configuration.");
}
//=================================================================================================//
ThermalBoundaryConfig MaterialBuilder::parseThermalBoundaryConfig(const json &config)
{
    ThermalBoundaryConfig thermal_boundary_config;
    thermal_boundary_config.boundary_type = config.get<std::string>();
    return thermal_boundary_config;
}
//=================================================================================================//
} // namespace SPH
