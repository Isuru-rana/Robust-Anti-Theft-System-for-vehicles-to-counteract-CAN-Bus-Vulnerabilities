idf_component_register(SRCS
                    "main.cpp"
                    INCLUDE_DIRS "."
                    REQUIRES j1939 mcp2515 json mqtt esp_wifi esp_event nvs_flash esp_netif)