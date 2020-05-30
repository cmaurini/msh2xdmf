#!/usr/bin/env python

import argparse
import meshio
import os
import numpy as np
import yaml

try:
    from dolfin import XDMFFile, Mesh, MeshValueCollection
    from dolfin.cpp.mesh import MeshFunctionSizet
except ImportError:
    print("Could not import dolfin. Continuing without Dolfin support.")


def msh2xdmf(mesh_name, dim=2, directory=".", write_labels=True):
    """
    Function converting a MSH mesh into XDMF files.
    The XDMF files are:
        - "domain.xdmf": the domain;
        - "boundaries.xdmf": the boundaries physical groups from GMSH;
    """

    # Read the input mesh
    msh = meshio.read("{}/{}".format(directory, mesh_name))

    # Generate the domain XDMF file
    export_domain(msh, dim, directory, filename=mesh_name[0:-4] + "_domain")

    # Generate the boundaries XDMF file
    export_boundaries(msh, dim, directory, filename=mesh_name[0:-4] + "_boundaries")

    # Display association table
    labels_dict = display_association_table(msh)
    if write_labels:
        labels_file = "{}/{}_labels.yml".format(directory, mesh_name[0:-4])
        with open(labels_file, 'w') as f:
            yaml.dump(labels_dict, f, default_flow_style=False)

def export_domain(msh, dim, directory, filename="domains"):
    """
    Export the domain XDMF file as well as the subdomains values.
    """
    # Set cell type
    if dim == 2:
        cell_type = "triangle"
    elif dim == 3:
        cell_type = "tetra"
    # Generate the cell block for the domain cells
    data_array = [arr for (t, arr) in msh.cells if t == cell_type]
    if len(data_array) == 0:
        print("WARNING: No domain physical group found.")
        return
    else:
        data = np.concatenate(data_array)
    cells = [
        meshio.CellBlock(
            type=cell_type,
            data=data,
            )
        ]
    # Generate the domain cells data (for the subdomains)
    try:
        cell_data = {
            "subdomains": [
                np.concatenate(
                    [
                        msh.cell_data["gmsh:physical"][i]
                        for i, cellBlock in enumerate(msh.cells)
                        if cellBlock.type == cell_type
                        ]
                    )
                ]
            }
    except KeyError:
        raise ValueError(
            """
            No physical group found for the domain.
            Define the domain physical group.
                - if dim=2, the domain is a surface
                - if dim=3, the domain is a volume
            """
            )

    # Generate a meshio Mesh for the domain
    domain = meshio.Mesh(
        points=msh.points[:, :dim],
        cells=cells,
        cell_data=cell_data,
    )
    # Export the XDMF mesh of the domain
    meshio.write(
        "{}/{}.xdmf".format(directory, filename),
        domain,
        file_format="xdmf"
        ) 


def export_boundaries(msh, dim, directory, filename="boundaries"):
    """
    Export the boundaries XDMF file.
    """
    # Set the cell type
    if dim == 2:
        cell_type = "line"
    elif dim == 3:
        cell_type = "triangle"
    # Generate the cell block for the boundaries cells
    data_array = [arr for (t, arr) in msh.cells if t == cell_type]
    if len(data_array) == 0:
        print("WARNING: No boundary physical group found.")
        return
    else:
        data = np.concatenate(data_array)
    boundaries_cells = [
        meshio.CellBlock(
            type=cell_type,
            data=data,
            )
        ]
    # Generate the boundaries cells data
    cell_data = {
        "boundaries": [
            np.concatenate(
                [
                    msh.cell_data["gmsh:physical"][i]
                    for i, cellBlock in enumerate(msh.cells)
                    if cellBlock.type == cell_type
                    ]
                )
            ]
        }
    # Generate the meshio Mesh for the boundaries physical groups
    boundaries = meshio.Mesh(
        points=msh.points[:, :dim],
        cells=boundaries_cells,
        cell_data=cell_data,
    )
    # Export the XDMF mesh of the lines boundaries
    meshio.write(
        "{}/{}.xdmf".format(directory, filename),
        boundaries,
        file_format="xdmf"
        )


def display_association_table(msh):
    """
    Display the association between the physical group label and the mesh
    value.
    """
    # Display the correspondance
    formatter = "|{:^20}|{:^20}|"
    topbot = "+{:-^41}+".format("", "")
    separator = "+{:-^20}+{:-^20}+".format("", "")

    # Display
    print(topbot)
    print(formatter.format("GMSH label", "MeshFunction value"))
    print(separator)

    labels_dict = {} 
    for label, arrays in msh.cell_sets.items():
        # Get the index of the array in arrays
        for i, array in enumerate(arrays):
            if array.size != 0:
                index = i
        # Get the value in cell_data for the corresponding array
        value = msh.cell_data["gmsh:physical"][index][0]
        # Display the association
        print(formatter.format(label, value))
        labels_dict[label] = int(value)
    print(topbot)
    return labels_dict


def import_mesh_from_xdmf(
        domain="domain.xdmf",
        boundaries="boundaries.xdmf",
        labels="labels.yaml",
        subdomains=False,
        dim=2,
        directory="."
        ):
    """
    Function importing a msh mesh and converting it into a dolfin mesh.

    Arguments:
        - domain (str): name of the domain XDMF file;
        - boundaries (str): name of the boundaries XDMF file;
        - dim (int): dimension of the domain;
        - subdomains (bool): true if there are subdomains, else false
        - directory (str): (optional) directory of the mesh;

    Output:
        - dolfin Mesh object containing the domain;
        - dolfin MeshFunction object containing the physical lines (dim=2) or
        surfaces (dim=3) defined in the msh file and the sub-domains;
        - a dictionary with labels for boundaries and subdomains
    """
    # Import the converted domain
    mesh = Mesh()
    with XDMFFile("{}/{}".format(directory, domain)) as infile:
        infile.read(mesh)
    # Import the boundaries
    boundaries_mvc = MeshValueCollection("size_t", mesh, dim=dim)
    with XDMFFile("{}/{}".format(directory, boundaries)) as infile:
        infile.read(boundaries_mvc, 'boundaries')
    boundaries_mf = MeshFunctionSizet(mesh, boundaries_mvc)
    # Import the subdomains
    if subdomains:
        subdomains_mvc = MeshValueCollection("size_t", mesh, dim=dim)
        with XDMFFile("{}/{}".format(directory, domain)) as infile:
            infile.read(subdomains_mvc, 'subdomains')
        subdomains_mf = MeshFunctionSizet(mesh, subdomains_mvc)
    # Import labels
    with open("{}/{}".format(directory, labels), 'r') as infile:
        labels = yaml.load(infile, Loader=yaml.FullLoader)
    # Return the Mesh and the MeshFunction objects
    if not subdomains:
        return mesh, boundaries_mf, labels
    else:
        return mesh, boundaries_mf, subdomains_mf, labels    
    print(labels)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "msh_file",
        help="input .msh file",
        type=str,
        )
    parser.add_argument(
        "-d",
        "--dimension",
        help="dimension of the domain",
        type=int,
        default=2,
        )
    args = parser.parse_args()
    # Get current directory
    current_directory = os.getcwd()
    # Conert the mesh
    msh2xdmf(args.msh_file, args.dimension, directory=current_directory)
