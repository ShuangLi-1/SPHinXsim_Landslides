# Aggregate simulation test subdirectories so ctest works from this level.

if(TARGET sph_simulation_2d)
    add_subdirectory(test_2d_simulation)
endif()

if(TARGET sph_simulation_3d)
    add_subdirectory(test_3d_simulation)
endif()
