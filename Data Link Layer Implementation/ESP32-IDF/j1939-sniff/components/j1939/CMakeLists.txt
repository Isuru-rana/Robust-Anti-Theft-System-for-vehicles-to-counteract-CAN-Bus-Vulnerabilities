idf_component_register(
    SRCS "j1939.cpp"
    INCLUDE_DIRS "include"
    REQUIRES driver mcp2515 freertos
)