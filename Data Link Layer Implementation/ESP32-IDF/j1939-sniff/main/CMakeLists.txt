idf_component_register(SRCS 
                    "main.cpp"
                    INCLUDE_DIRS "."
                    REQUIRES nvs_flash j1939 mcp2515)