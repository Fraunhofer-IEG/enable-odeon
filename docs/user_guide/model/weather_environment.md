!!! warning "Under Construction"

    This documentation is still under construction and will receive major 
    additions and changes in the future. Please be considerate with us and the 
    documentation. However, if you already have any tips and remarks or if you 
    miss some super important aspects, we'd love to hear from you.

!!! warning "To-dos"

    - Content of class `Environment`
    - One weather per branch, or per object

# Weather and Environment

Environmental influences can limit the applicable technologies within an 
energy system. The required data is stored within each branch as objects.

## Weather class

All important environmental data in Odeon is contained in the Weather class.
This includes several temperatures like ambient temeperature or soil 
temperatures, irradiances and wind data. As an Object class of Odeon it 
provides the necessary weather information for the calculation of energy 
demands and renewable energy production.

The Data is stored as timeseries. The following data can be stored:

- Temperature Data:
  - Ambient Temperature
  - Soil Temperature
  - Underground Temperature
- Irradiance Data:
  - Global Horizontal Irradiance
  - Diffuse Horizontal Irradiance
  - Direct Normal Irradiance
- Wind Data:
  - Wind Speed
  - Wind Direction
- Pressure Data
- Solar Position