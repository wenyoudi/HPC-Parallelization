# Integrate the pinned B implementation without changing its source or CMake.
add_library(member_b_mpi_core STATIC ${PROJECT_SOURCE_DIR}/references/mpi/src/mpi_poisson.cpp)
target_include_directories(member_b_mpi_core PUBLIC ${PROJECT_SOURCE_DIR}/references/mpi/include)
target_link_libraries(member_b_mpi_core PUBLIC poisson_core MPI::MPI_CXX)
target_compile_options(member_b_mpi_core PRIVATE -Wall -Wextra -Wpedantic)
add_executable(mpi ${PROJECT_SOURCE_DIR}/references/mpi/src/mpi_main.cpp)
target_link_libraries(mpi PRIVATE member_b_mpi_core)

add_library(hybrid_core STATIC ${PROJECT_SOURCE_DIR}/src/hybrid_poisson.cpp)
# Deliberately exclude root include/: its standalone OpenMP poisson.hpp has a
# different interface. B and hybrid use A's unchanged header through poisson_core.
target_include_directories(hybrid_core PUBLIC ${PROJECT_SOURCE_DIR}/include/hybrid)
target_link_libraries(hybrid_core PUBLIC member_b_mpi_core OpenMP::OpenMP_CXX)
target_compile_options(hybrid_core PRIVATE -Wall -Wextra -Wpedantic)
add_executable(hybrid ${PROJECT_SOURCE_DIR}/src/hybrid_main.cpp)
target_link_libraries(hybrid PRIVATE hybrid_core)

add_executable(test_hybrid_rows ${PROJECT_SOURCE_DIR}/tests/test_hybrid_rows.cpp)
target_include_directories(test_hybrid_rows PRIVATE ${PROJECT_SOURCE_DIR}/include/hybrid)
target_link_libraries(test_hybrid_rows PRIVATE OpenMP::OpenMP_CXX)
add_test(NAME hybrid_local_rows COMMAND test_hybrid_rows)
set_tests_properties(hybrid_local_rows PROPERTIES ENVIRONMENT "OMP_DYNAMIC=FALSE;OMP_DISPLAY_AFFINITY=FALSE")
