from __future__ import print_function

from openmdao.api import Problem, pyOptSparseDriver, SqliteRecorder
from OptimizationGroup import OptAEP
from wakeexchange.GeneralWindFarmComponents import calculate_boundary

import time
import numpy as np
import matplotlib.pyplot as plt
import chaospy as cp
import json
import argparse
import windfarm_setup
import distributions


def get_args():
    parser = argparse.ArgumentParser(description='Run statistics convergence')
    parser.add_argument('--windspeed_ref', default=8, type=float, help='the wind speed for the wind direction case')
    parser.add_argument('--winddirection_ref', default=225, type=float, help='the wind direction for the wind speed case')
    parser.add_argument('-l', '--layout', default='optimized', help="specify layout ['amalia', 'optimized', 'grid', 'random', 'test']")
    parser.add_argument('--offset', default=0, type=int, help='offset for starting direction. offset=[0, 1, 2, Noffset-1]')
    parser.add_argument('--Noffset', default=10, type=int, help='number of starting directions to consider')
    parser.add_argument('--verbose', action='store_true', help='Includes results for every run in the output json file')
    parser.add_argument('--version', action='version', version='Statistics convergence 0.0')
    args = parser.parse_args()
    # print args
    # print args.offset
    return args


if __name__ == "__main__":

    #########################################################################
    # method_dict = {}
    # keys of method_dict:
    #     'method' = 'dakota', 'rect' or 'chaospy'  # 'chaospy needs updating
    #     'wake_model = 'floris', 'jensen', 'gauss', 'larsen' # larsen is not working
    #     'coeff_method' = 'quadrature', 'sparse_grid' or 'regression'
    #     'uncertain_var' = 'speed', 'direction' or 'direction_and_speed'
    #     'layout' = 'amalia', 'optimized', 'grid', 'random', 'test', 'layout1', 'layout2', 'layout3'
    #     'distribution' = a distribution object
    #     'dakota_filename' = 'dakotaInput.in', applicable for dakota method
    #     'offset' = [0, 1, 2, Noffset-1]
    #     'Noffset' = 'number of starting directions to consider'

    # Get arguments
    args = get_args()

    # Specify the rest of arguments
    # method_dict = {}
    method_dict = vars(args)  # Start a dictionary with the arguments specified in the command line
    method_dict['method']           = 'rect'
    method_dict['uncertain_var']    = 'direction'
    # select model: floris, jensen, gauss, larsen (larsen not working yet) TODO get larsen model working
    method_dict['wake_model']       = 'floris'
    # method_dict['dakota_filename']  = 'dakotageneral.in'
    method_dict['dakota_filename']  = 'dakotageneralPy.in'  # Interface with python support
    method_dict['coeff_method']     = 'quadrature'

    # Specify the distribution according to the uncertain variable
    if method_dict['uncertain_var'] == 'speed':
        dist = distributions.getWeibull()
        method_dict['distribution'] = dist
    elif method_dict['uncertain_var'] == 'direction':
        dist = distributions.getWindRose()
        method_dict['distribution'] = dist
    elif method_dict['uncertain_var'] == 'direction_and_speed':
        dist1 = distributions.getWindRose()
        dist2 = distributions.getWeibull()
        dist = cp.J(dist1, dist2)
        method_dict['distribution'] = dist
    else:
        raise ValueError('unknown uncertain_var option "%s", valid options "speed", "direction" or "direction_and_speed".' %method_dict['uncertain_var'])

    ### Set up the wind speeds and wind directions for the problem ###
    n = 20  # number of points, i.e., number of winddirections and windspeeds pairs
    points = windfarm_setup.getPoints(method_dict, n)
    winddirections = points['winddirections']
    windspeeds = points['windspeeds']
    weights = points['weights']  # This might be None depending on the method.
    N = winddirections.size  # actual number of samples

    print('Locations at which power is evaluated')
    print('\twindspeed \t winddirection')
    for i in range(N):
        print(i+1, '\t', '%.2f' % windspeeds[i], '\t', '%.2f' % winddirections[i])

    # Turbines layout
    turbineX, turbineY = windfarm_setup.getLayout(method_dict['layout'])
    locations = np.column_stack((turbineX, turbineY))
    nTurbs = turbineX.size

    # generate boundary constraint
    boundaryVertices, boundaryNormals = calculate_boundary(locations)
    nVertices = boundaryVertices.shape[0]
    print('boundary vertices', boundaryVertices)

    minSpacing = 2.                         # number of rotor diameters

    # initialize problem
    prob = Problem(root=OptAEP(nTurbines=nTurbs, nDirections=N, minSpacing=minSpacing, nVertices=nVertices, method_dict=method_dict))

    # set up optimizer
    # Scale everything (variables, objective, constraints) to make order 1.
    diameter = 126.4  # meters, used in the scaling
    prob.driver = pyOptSparseDriver()
    prob.driver.options['optimizer'] = 'SNOPT'
    prob.driver.add_objective('obj', scaler=1E-8)

    # set optimizer options
    prob.driver.opt_settings['Verify level'] = -1  # 3
    prob.driver.opt_settings['Print file'] = 'SNOPT_print_exampleOptAEP.out'
    prob.driver.opt_settings['Summary file'] = 'SNOPT_summary_exampleOptAEP.out'
    prob.driver.opt_settings['Major iterations limit'] = 1000
    prob.driver.opt_settings['Major optimality tolerance'] = 1E-4
    prob.driver.opt_settings['Major feasibility tolerance'] = 1E-4
    prob.driver.opt_settings['Minor feasibility tolerance'] = 1E-4
    prob.driver.opt_settings['Function precision'] = 1E-5

    # select design variables
    prob.driver.add_desvar('turbineX', adder=-turbineX, scaler=1.0/diameter)
    prob.driver.add_desvar('turbineY', adder=-turbineY, scaler=1.0/diameter)
    # for direction_id in range(0, N):
    #     prob.driver.add_desvar('yaw%i' % direction_id, lower=-30.0, upper=30.0, scaler=1.0)

    # add constraints
    prob.driver.add_constraint('sc', lower=np.zeros(((nTurbs-1.)*nTurbs/2.)), scaler=1.0/((20*diameter)**2))
    prob.driver.add_constraint('boundaryDistances', lower=np.zeros(nVertices*nTurbs), scaler=1.0/(10*diameter))

    # Reduces time of computation
    prob.root.ln_solver.options['single_voi_relevance_reduction'] = True

    # Set up a recorder
    recorder = SqliteRecorder('optimization.sqlite')
    # recorder.options['record_params'] = True
    # recorder.options['record_metadata'] = True
    prob.driver.add_recorder(recorder)

    tic = time.time()
    prob.setup(check=False)
    toc = time.time()

    # print the results
    print('FLORIS setup took %.03f sec.' % (toc-tic))

    # assign initial values to variables
    prob['windSpeeds'] = windspeeds
    prob['windDirections'] = winddirections
    prob['windWeights'] = weights

    prob['turbineX'] = turbineX
    prob['turbineY'] = turbineY

    # provide values for the hull constraint
    prob['boundaryVertices'] = boundaryVertices
    prob['boundaryNormals'] = boundaryNormals

    # run the problem
    print(prob, 'start FLORIS run')
    tic = time.time()
    prob.run()
    toc = time.time()

    prob.cleanup()  # this closes all recorders

    # print the results
    print('FLORIS Opt. calculation took %.03f sec.' % (toc-tic))

    print('turbine X positions in wind frame (m): %s' % prob['turbineX'])
    print('turbine Y positions in wind frame (m): %s' % prob['turbineY'])
    print('wind farm power in each direction (kW): %s' % prob['Powers'])
    print('AEP (kWh): %s' % prob['mean'])

    xbounds = [min(turbineX), min(turbineX), max(turbineX), max(turbineX), min(turbineX)]
    ybounds = [min(turbineY), max(turbineY), max(turbineY), min(turbineY), min(turbineX)]

    np.savetxt('AmaliaOptimizedXY.txt', np.c_[prob['turbineX'], prob['turbineY']], header="turbineX, turbineY")

    # Save details of the simulation
    obj = {'mean': prob['mean']/1e6, 'std': prob['std']/1e6, 'samples': N, 'winddirections': winddirections.tolist(),
           'windspeeds': windspeeds.tolist(), 'power': prob['Powers'].tolist(),
           'method': method_dict['method'], 'uncertain_variable': method_dict['uncertain_var'],
           'layout': method_dict['layout'], 'turbineX': turbineX.tolist(), 'turbineY': turbineY.tolist(),
           'turbineXopt': prob['turbineX'].tolist(), 'turbineYopt': prob['turbineY'].tolist()}
    jsonfile = open('record_opt.json', 'w')
    json.dump(obj, jsonfile, indent=2)
    jsonfile.close()

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
