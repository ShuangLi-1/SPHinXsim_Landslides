/**
 * @file simulation.cpp
 * @brief 2D simulation examples driven by a JSON configuration file.
 * @details All simulation parameters (domain, fluid, wall, gravity, solver,
 *          end time) are loaded from data/config.json via the SPHSimulation
 *          facade.  No hard-coded physics constants appear in this file.
 * @author Xiangyu Hu
 */
#include "sph_simulation.h"
#include <gtest/gtest.h>
/*
TEST(simulations, dambreak)
{
    SPH::SPHSimulation sim("./input/dambreak.json");
    sim.resetOutputRoot("./dambreak");
    sim.buildGeometries();
    sim.generateParticles();
    sim.buildSimulation();
    sim.initializeSimulation();
    sim.run();
}

TEST(simulations, filling_tank)
{
    SPH::SPHSimulation sim("./input/filling_tank.json");
    sim.resetOutputRoot("./filling_tank", true);
    sim.buildGeometries();
    sim.generateParticles();
    sim.buildSimulation();
    sim.initializeSimulation();
    sim.run();
}

TEST(simulations, milling)
{
    SPH::SPHSimulation sim("./input/milling.json");
    sim.resetOutputRoot("./milling", true);
    sim.buildGeometries();
    sim.generateParticles();
    sim.buildSimulation();
    sim.initializeSimulation();
    sim.run();
}
*/
TEST(simulations, heat_transfer)
{
    SPH::SPHSimulation sim("./input/heat_transfer.json");
    sim.resetOutputRoot("./heat_transfer", true);
    sim.buildGeometries();
    sim.generateParticles();
    sim.buildSimulation();
    sim.initializeSimulation();
    sim.run();
}

TEST(simulations, t_junction)
{
    SPH::SPHSimulation sim("./input/t_junction.json");
    sim.resetOutputRoot("./t_junction", true);
    sim.buildGeometries();
    sim.generateParticles();
    sim.buildSimulation();
    sim.initializeSimulation();
    sim.run();
}
