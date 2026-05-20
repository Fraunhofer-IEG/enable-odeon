!!! warning "Under Construction"

    This documentation is still under construction and will receive major 
    additions and changes in the future. Please be considerate with us and the 
    documentation. However, if you already have any tips and remarks or if you 
    miss some super important aspects, we'd love to hear from you.

# Options and Decisions

Decisions in Odeon describe options to buy and build a device or to determine the scale of a device. The decision is made based on set economical data. The Options can be used as a decision variable for optimization calculations.

## Decisions

### State of the decision

In the Code of Odeon, decisions are divided by different states which show the current stage of the decision and the device.

- FIXED: FIXED describes a device that is predefined and cannot be changed in a decision process. Optimization or design calculations have therefore no impact an influence on the device.
- UNDECIDED_EXISTING: This state describes existing devices that could be replaced. The actual decision has not been made yet and the replacement can be a decision variable of optimizations.
- UNDECIDED_OPTION: UNDECIDED_OPTION describes an unexisting device that could be build. Optimization algorythms or design calculation can decide whether the device is build or not.
- UNDECIDED_SCALING: The state UNDECIDED_SCALING describes a device, that is to be build, but the scaling decision is not yet taken. The Optimization can decide the exact design size.
- DECIDED_FOR: This state describes a device, that decided for and is now build.
- DECIDED_AGAINST: DECIDED_AGAINST are devices, that has been decided against and have not been build.
- DECIDED_SCALING: This state describes a build device with scaling decisions already taken.
- UNKNOWN: Devices with an unknown state.

### decision types

Decision Types describe the properties of the decision. It can be dependent on different constraints, other choices or existing and non-existing devices.

- INDEPENDENT: The decision for or against a device do not depent on other faktors or constraints.
- INDEPENDENT_SCALING: The decision on the dimension of a device without other constrains than that their existence is fixed.
- ONLY_ONE: This decision includes the replacement of already build devices with the new device.
- LINEAR_COMPETITION: Tis Type describs non-existing devices, that are competing linearly for their maximum dimension.

