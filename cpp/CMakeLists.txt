cmake_minimum_required(VERSION 3.15)
project(mu2e_sender VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Compiler warnings ──────────────────────────────────────────────────────
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ── Library ────────────────────────────────────────────────────────────────
add_library(mu2e_sender
    src/mu2e_sender.cpp
)

target_include_directories(mu2e_sender
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

# Shared library version info
set_target_properties(mu2e_sender PROPERTIES
    VERSION   ${PROJECT_VERSION}
    SOVERSION ${PROJECT_VERSION_MAJOR}
)

# ── CLI tool ───────────────────────────────────────────────────────────────
add_executable(mu2e_send
    tools/mu2e_send.cpp
)

target_link_libraries(mu2e_send PRIVATE mu2e_sender)

# ── Install rules ──────────────────────────────────────────────────────────
include(GNUInstallDirs)

install(TARGETS mu2e_sender mu2e_send
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)

install(FILES include/mu2e_sender.h
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
