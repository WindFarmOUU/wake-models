from __future__ import print_function

from openmdao.api import Problem, pyOptSparseDriver
from OptimizationGroup import OptAEP
from florisse import config

import distributions
import time
import numpy as np
import pylab as plt

import cProfile
import quadrature_rules


import sys

if __name__ == "__main__":

    config.floris_single_component = True

    ######################### for MPI functionality #########################
    from openmdao.core.mpi_wrap import MPI

    if MPI: # pragma: no cover
        # if you called this script with 'mpirun', then use the petsc data passing
        from openmdao.core.petsc_impl import PetscImpl as impl

    else:
        # if you didn't use 'mpirun', then use the numpy data passing
        from openmdao.api import BasicImpl as impl

    def mpi_print(prob, *args):
        """ helper function to only print on rank 0 """
        if prob.root.comm.rank == 0:
            print(*args)

    prob = Problem(impl=impl)

    size = 4 # number of processors (and number of wind directions to run)

    #########################################################################
    # define turbine size
    rotor_diameter = 126.4  # (m)

    # define turbine locations in global reference frame
    # original example case
    # turbineX = np.array([1164.7, 947.2,  1682.4, 1464.9, 1982.6, 2200.1])   # m
    # turbineY = np.array([1024.7, 1335.3, 1387.2, 1697.8, 2060.3, 1749.7])   # m

    # Scaling grid case
    #nRows = int(sys.argv[1])     # number of rows and columns in grid
    nRows = 2
    spacing = 5     # turbine grid spacing in diameters

    # Set up position arrays
    points = np.linspace(start=spacing*rotor_diameter, stop=nRows*spacing*rotor_diameter, num=nRows)
    xpoints, ypoints = np.meshgrid(points, points)
    turbineX = np.ndarray.flatten(xpoints)
    turbineY = np.ndarray.flatten(ypoints)

    # initialize input variable arrays
    nTurbs = turbineX.size
    rotorDiameter = np.zeros(nTurbs)
    axialInduction = np.zeros(nTurbs)
    Ct = np.zeros(nTurbs)
    Cp = np.zeros(nTurbs)
    generatorEfficiency = np.zeros(nTurbs)
    yaw = np.zeros(nTurbs)
    minSpacing = 2.                         # number of rotor diameters

    # define initial values
    for turbI in range(0, nTurbs):
        rotorDiameter[turbI] = rotor_diameter      # m
        axialInduction[turbI] = 1.0/3.0
        Ct[turbI] = 4.0*axialInduction[turbI]*(1.0-axialInduction[turbI])
        Cp[turbI] = 0.7737/0.944 * 4.0 * 1.0/3.0 * np.power((1 - 1.0/3.0), 2)
        generatorEfficiency[turbI] = 0.944
        yaw[turbI] = 0.     # deg.

    # Define flow properties
    # Get the points at which to evaluate the wind farm

    method = 'rect'
    dist = distributions.getWindRose()

    method_dict = {}
    method_dict['distribution'] = dist
    n = 30
    points, unused = quadrature_rules.rectangle(n, method_dict['distribution'])
    windspeeds = np.ones(n)*8
    windDirections = points[0]     # m/s
    
    air_density = 1.1716    # kg/m^3
    #windDirections = np.linspace(0, 270, size)
    #windFrequencies = np.ones_like(windDirections)*1.0/size
    

    # initialize problem
    prob = Problem(impl=impl, root=OptAEP(nTurbines=nTurbs, nDirections=windDirections.size,                                        minSpacing=minSpacing, use_rotor_components=False, datasize=0, differentiable=True, force_fd=False, nSamples=0, method=method, method_dict=method_dict))

    # set up optimizer
    prob.driver = pyOptSparseDriver()
    prob.driver.options['optimizer'] = 'SNOPT'
    prob.driver.add_objective('obj', scaler=1E-8)

    # set optimizer options
    prob.driver.opt_settings['Verify level'] = 3
    prob.driver.opt_settings['Print file'] = 'SNOPT_print_exampleOptAEP.out'
    prob.driver.opt_settings['Summary file'] = 'SNOPT_summary_exampleOptAEP.out'
    prob.driver.opt_settings['Major iterations limit'] = 1000

    # select design variables
    prob.driver.add_desvar('turbineX', lower=np.ones(nTurbs)*min(turbineX), upper=np.ones(nTurbs)*max(turbineX), scaler=1E-2)
    prob.driver.add_desvar('turbineY', lower=np.ones(nTurbs)*min(turbineY), upper=np.ones(nTurbs)*max(turbineY), scaler=1E-2)
    for direction_id in range(0, windDirections.size):
        prob.driver.add_desvar('yaw%i' % direction_id, lower=-30.0, upper=30.0, scaler=1E-1)

    # add constraints
    prob.driver.add_constraint('sc', lower=np.zeros(((nTurbs-1.)*nTurbs/2.)), scaler=1.0/rotor_diameter)

    tic = time.time()
    prob.setup(check=False)
    toc = time.time()

    # print the results
    mpi_print(prob, ('FLORIS setup took %.03f sec.' % (toc-tic)))

    # time.sleep(10)
    # assign initial values to design variables
    prob['turbineX'] = turbineX
    prob['turbineY'] = turbineY
    for direction_id in range(0, windDirections.size):
        prob['yaw%i' % direction_id] = yaw

    # assign values to constant inputs (not design variables)
    prob['rotorDiameter'] = rotorDiameter
    prob['axialInduction'] = axialInduction
    prob['generatorEfficiency'] = generatorEfficiency
    # prob['windSpeeds'] = np.ones(windDirections.size)*wind_speed
    prob['windSpeeds'] = windspeeds
    prob['air_density'] = air_density
    prob['windDirections'] = windDirections
    # prob['windFrequencies'] = windFrequencies
    prob['Ct_in'] = Ct
    prob['Cp_in'] = Cp

    # set options
    # prob['floris_params:FLORISoriginal'] = True
    # prob['floris_params:CPcorrected'] = False
    # prob['floris_params:CTcorrected'] = False

    # run the problem
    mpi_print(prob, 'start FLORIS run')
    tic = time.time()
    # cProfile.run('prob.run()')
    prob.run()
    toc = time.time()

    # print the results
    mpi_print(prob, ('FLORIS Opt. calculation took %.03f sec.' % (toc-tic)))

    for direction_id in range(0, windDirections.size):
        mpi_print(prob,  'yaw%i (deg) = ' % direction_id, prob['yaw%i' % direction_id])
    # for direction_id in range(0, windDirections.size):
        # mpi_print(prob,  'velocitiesTurbines%i (m/s) = ' % direction_id, prob['velocitiesTurbines%i' % direction_id])
    # for direction_id in range(0, windDirections.size):
    #     mpi_print(prob,  'wt_power%i (kW) = ' % direction_id, prob['wt_power%i' % direction_id])

    mpi_print(prob,  'turbine X positions in wind frame (m): %s' % prob['turbineX'])
    mpi_print(prob,  'turbine Y positions in wind frame (m): %s' % prob['turbineY'])
    mpi_print(prob,  'wind farm power in each direction (kW): %s' % prob['dirPowers'])
    mpi_print(prob,  'AEP (kWh): %s' % prob['AEP'])

    xbounds = [min(turbineX), min(turbineX), max(turbineX), max(turbineX), min(turbineX)]
    ybounds = [min(turbineY), max(turbineY), max(turbineY), min(turbineY), min(turbineX)]

    plt.figure()
    plt.plot(turbineX, turbineY, 'ok', label='Original')
    plt.plot(prob['turbineX'], prob['turbineY'], 'og', label='Optimized')
    plt.plot(xbounds, ybounds, ':k')
    for i in range(0, nTurbs):
        plt.plot([turbineX[i], prob['turbineX'][i]], [turbineY[i], prob['turbineY'][i]], '--k')
    plt.legend()
    plt.xlabel('Turbine X Position (m)')
    plt.ylabel('Turbine Y Position (m)')
    plt.show()

