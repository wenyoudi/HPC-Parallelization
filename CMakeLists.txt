cmake_minimum_required(VERSION 3.16)
project(Project3OpenMP LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
# Explicit Release settings; no fast-math or architecture-specific tuning.
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")
find_package(OpenMP REQUIRED COMPONENTS CXX)
find_package(Python3 3.8 REQUIRED COMPONENTS Interpreter)
enable_testing()

add_executable(openmp src/openmp.cpp)
add_executable(test_rows tests/test_rows.cpp)
foreach(target openmp test_rows)
    target_include_directories(${target} PRIVATE include)
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    target_link_libraries(${target} PRIVATE OpenMP::OpenMP_CXX)
endforeach()
add_test(NAME local_rows COMMAND test_rows)
add_test(NAME openmp_numerical COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_openmp.py --solver $<TARGET_FILE:openmp>)
set_tests_properties(local_rows openmp_numerical PROPERTIES
    ENVIRONMENT "OMP_DYNAMIC=FALSE;OMP_DISPLAY_AFFINITY=FALSE" TIMEOUT 300)

option(BUILD_MPI_SMOKE "Build MPI launch/thread-support smoke test (not an MPI solver)" OFF)
if(BUILD_MPI_SMOKE)
    find_package(MPI REQUIRED COMPONENTS CXX)
    add_executable(mpi_smoke tests/mpi_smoke.cpp)
    target_link_libraries(mpi_smoke PRIVATE MPI::MPI_CXX)
    target_compile_options(mpi_smoke PRIVATE -Wall -Wextra -Wpedantic)
endif()
