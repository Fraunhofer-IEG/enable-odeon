!!! warning "Under Construction"

    This documentation is still under construction and will receive major 
    additions and changes in the future. Please be considerate with us and the 
    documentation. However, if you already have any tips and remarks or if you 
    miss some super important aspects, we'd love to hear from you.

# Energy System

- This page gives an overview on how core aspects of energy systems can be described in Odeon.
- Arguably the most essential viewpoint on energy systems might be the topology of energy flows and conversion. In Odeon, these aspects are covered by the class of `Component`s, `Socket`s, `Medium`s and `Link`s. Find an introduction on the page [Components and Energy Flow](components.md)
- Odeon also includes a set of premodelled energy system components like heat pumps, PV plants etc. Such concretizations of nodes in an energy system topology are called `Device`s. Per definition in Odeon, a `Device` is also an [`Asset`](../assets/introduction_assets.md) and as such can store economic properties and decision states. The page [Devices](devices.md) gives an overview.
- Energy networks like the electricity grid and district heating and cooling networks (DHC) can be modelled with the Odeon class `Network`. This will comprise detailed description of the network topology, geometry and energy transport by using pipes, cables, junctions etc. Such networks are covered in the subsection [Network](networks/introduction_networks.md).
- If a more general description of networks is required, or if you need to model the combination of one or multiple networks and adjacent inferior energy systems of production sites and consumption locations, see the page [Integrated Modelling](integrated_modelling.md) for tips.