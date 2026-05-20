!!! warning "Under Construction"

    This documentation is still under construction and will receive major 
    additions and changes in the future. Please be considerate with us and the 
    documentation. However, if you already have any tips and remarks or if you 
    miss some super important aspects, we'd love to hear from you.

# Integrated Modelling

## Linking buildings and/or central devices with district heating networks

Attachments to `DhnNodes` can be

- `Building`s
- `BuildingDhnConnection`s

to depict buildings connected to the district heating network, or

- `Site`s
- `TransferStation`s

to depict central devices and production sites connected to the district heating network. The former of each represent a more general modeling style

An example could look like this - the edges between the network nodes are not shown:

```mermaid
flowchart TD
    Building --> EnergySystem
    DhnNode -. attachment .-> BuildingDhnConnection
    Dhn -- nodes[] --> DhnNode
    Dhn -- nodes[] --> DhnNode2[DhnNode]
    DhnNode2 -. attachment .-> TransferStation
    Site --> EnergySystem2[EnergySystem]
    subgraph Fantom2[Fantom]
    EnergySystem2 -- devices[] --> TransferStation
    EnergySystem2 -- devices[] --> Heatpump
    end
    subgraph Fantom
    EnergySystem -- devices[] --> HeatingDemand
    EnergySystem -- devices[] --> SolarthermalDevice
    EnergySystem -- devices[] --> BuildingDhnConnection
    end
```

## Describing district heating networks by `Device`s, or by `Pipe`s

### Representation #1: By `DhnEdge`s and `DhnNode`s with attachments. 

By this approach, network topology and attributes like pressures, velocities etc. can be modelled in detail

```mermaid
graph LR
    DhnNode2[DhnNode] -. attachment .-> TransferStation
    DhnNode -. attachment .-> BuildingDhnConnection
    DhnEdge -.-> |node_from| DhnNode2
    DhnEdge -.-> |node_to| DhnNode
    DistrictHeatingNetwork --> |"nodes[]"| DhnNode
    DistrictHeatingNetwork --> |"nodes[]"| DhnNode2
    DistrictHeatingNetwork --> |"edges[]"| DhnEdge
```

### Representation #2: By `Device`s

With this approach, topology is neglected and distribution is described in a star-like manner from a central `DhnDistribution` object (Bus, lossless) and `DhnTransport` connectors (Transformers, lossy). This approach is more focused on economic properties and energy system-level flows than on technical and geometrical properties of individual pipes.

```mermaid
flowchart LR
    subgraph 1[EnergySystem of a Vicinity]
    DhnDistribution
    DhnTransport
    DhnTransport2[DhnTransport]
    DhnTransport3[DhnTransport]
    end

    subgraph 2[EnergySystem of a Site]
    HeatSource
    TransferStation
    end

    subgraph 3[EnergySystem of a Building]
    BuildingDhnConnection ==> HeatingDemand
    end

    subgraph 4[EnergySystem of a Building]
    BuildingDhnConnection2[BuildingDhnConnection] ==> HeatingDemand2[HeatingDemand]
    end

    DhnDistribution ==>|flow| DhnTransport
    DhnDistribution ==>|flow| DhnTransport3
    DhnTransport ==> |flow| BuildingDhnConnection 
    DhnTransport3 ==> |flow| BuildingDhnConnection2
    DhnTransport2[DhnTransport] ==> |flow| DhnDistribution
    TransferStation ==> |flow| DhnTransport2
    HeatSource ==> |flow| TransferStation
```

At the same time, A `ThermalGrid` (which is a `CombiAsset`) is the parent of the `ThermalGridTransport`s, `ThermalGridDistribution`s. This allows to set economic properties to the `ThermalGrid` as well to its sub-assets.

A `ThermalGrid` can contain any number of `ThermalGridTransport`s and `ThermalGridDistribution`s. It's the user's responsibility to make sure that these are linked in a correct way, especially in a way that is not contradicting to any topological representation of the network by nodes, edges, and attachments.


```mermaid
classDiagram
    class ThermalGrid["ThermalGrid(CombiAsset)"] {
        - district_heating_network: Union[DistrictHeatingNetwork, None]
        - transfer_stations() List[TransferStation]
        - building_dhn_connections() List[BuildingThermalGridConnection]
        - thermal_grid_transports() List[ThermalGridTransport]
        - thermal_grid_distributions() List[ThermalGridTransport]
        - sites() List[Site]
        - structures() List[Structure]
        - dhn_nodes() List[DhnNode]
        - dhn_edges() List[DhnEdge]
    }
    class ThermalGridTransport["ThermalGridTransport(Transformer)"] {
        - dhn_nodes: List[DhnNode]
        - dhn_edges: List[DhnEdge]
    }
    class ThermalGridDistribution["ThermalGridDistribution(Bus)"] {
        - dhn_nodes: List[DhnNode]
        - dhn_edges: List[DhnEdge]
        - thermal_grid_transports() List[ThermalGridTransport]
    }
    ThermalGrid *-- ThermalGridTransport
    ThermalGrid *-- ThermalGridDistribution
    ThermalGridTransport .. ThermalGridDistribution : via Sockets
    
    class TransferStation["TransferStation(Transformer)"] {
    }
    class BuildingDhnConnection["BuildingDhnConnection(Transformer)"] {
    }
    ThermalGridTransport .. BuildingDhnConnection : via Sockets
    ThermalGridTransport .. TransferStation : via Sockets
    
    class DistrictHeatingNetwork["DistrictHeatingNetwork(Network)"] {
    }
    class DhnNode {
    }
    class DhnEdge {
    }
    DistrictHeatingNetwork *-- DhnNode
    DistrictHeatingNetwork *-- DhnEdge

    ThermalGrid <--> DistrictHeatingNetwork
    ThermalGridTransport --> DhnNode
    ThermalGridTransport --> DhnEdge
    ThermalGridDistribution --> DhnNode
    ThermalGridDistribution --> DhnEdge

```

The properties `dhn_nodes` and `dhn_edges` on the classes `ThermalGridDistribution` and `ThermalGridTransport` can be used to store information on which nodes and edges (and junctions and pipes) are represented by each Device.

It's noteworthy that `ThermalGridTransport`s and `ThermalGridDistribution`s could be used to exactly mirror the topology formed by `DhnEdge`s and `DhnNode`s, this would be the case if all `DhnEdge`s map to exactly one `ThermalGridTransport` and vice versa, and all `DhnNode`s map to exactly one `ThermalGridDistribution` and vice versa.


## Linking buildings and/or central devices with electricity grids

```mermaid
flowchart TD
    Building --> EnergySystem
    DegNode -. attachment .-> BuildingDegConnection
    Deg -- nodes[] --> DegNode
    Deg -- nodes[] --> DegNode2[DegNode]
    DegNode2 -. attachment .-> Transformer
    Site --> EnergySystem2[EnergySystem]
    subgraph Fantom2[Fantom]
    EnergySystem2 -- devices[] --> Transformer
    EnergySystem2 -- devices[] --> PhotovoltaicDevice
    end
    subgraph Fantom
    EnergySystem -- devices[] --> PhotovoltaicDevice2[PhotvoltaicDevice]
    EnergySystem -- devices[] --> Wallbox
    EnergySystem -- devices[] --> BuildingDegConnection
    end
```


## Placing devices in the vicinity

```mermaid
flowchart TD
    Vicinity --> EnergySystem3[EnergySystem]
    EnergySystem3 -- devices[] --> ChargingStation
``````
    