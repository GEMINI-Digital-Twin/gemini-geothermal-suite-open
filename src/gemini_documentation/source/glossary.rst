.. _gemini-glossary:

Glossary
===========================

This page provides an overview of the definitions of various terms used in this manual and the GEMINI platform itself.


Application
    An interactive tool within the platform that can be used to execute on-demand calculations and/or visualizations for detailed analyses of various assets or processes of the physical system. 


Asset
    A part of the physical system, in many cases corresponding to a unit operation, that can be treated indepently or as a subcomponent of a larger system. The digital counterpart of an asset in the diagram builder is referred to as a "unit". 


Calculated Data
    The output tags computed by the modules. Stored separately from the plant data to prevent conflicts or accidental overwriting of data.


Database
    An external storage for tag values.


Diagram
    The digital representation of a physical plant resembling a process flow diagram. Consists of a collection of units connected to each other.


Diagram builder
    The application used to create the diagram of the physical plant. 


GUI
    Acronym for Graphical User Interface, the visual interface through which a user can interact with the GEMINI framework, modules, and applications.


Model
    A script that takes a set of inputs, performs a calculation, and returns a set of outputs. Static models are pure input-output models, while dynamic models have an internal state that is tracked and updated everytime the model is executed.


Module
    A periodically executed script designed to automatically call a (collection of) model(s) to provide a specific utility to the user. A typical module reads one or more database tags, performs calculations by calling one or more models with the tag values, and writes the results to other database tags.


Parameter
    A configuration variable associated with a specific unit.


Plant
    The entirety of all assets/units in a system combined. A geothermal doublet would be considered a plant.


Project
    An instance of a specific combination of components, settings, and data of plant or individual asset for which the digital twin is set up.


Tag
    A named numeric data item in the database. For each tag, a history of time stamped numerical values is stored in the database. It is used to store a measured or computed signal as a function of time.


Unit
    Digital representation of an asset, i.e. the blocks in the diagram builder.