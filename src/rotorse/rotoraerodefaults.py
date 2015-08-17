#!/usr/bin/env python
# encoding: utf-8
"""
aerodefaults.py

Created by Andrew Ning on 2013-10-07.
Copyright (c) NREL. All rights reserved.
"""

import numpy as np
from math import pi, gamma
from openmdao.main.datatypes.api import Int, Float, Array, Str, List, Enum, VarTree, Bool
from openmdao.main.api import Component, Assembly

from ccblade import CCAirfoil, CCBlade as CCBlade_PY
from commonse.utilities import sind, cosd, smooth_abs, smooth_min, hstack, vstack, linspace_with_deriv
from rotoraero import GeomtrySetupBase, AeroBase, DrivetrainLossesBase, CDFBase, \
    VarSpeedMachine, FixedSpeedMachine, RatedConditions, common_configure
from akima import Akima
import pyXLIGHT
from airfoilprep import Airfoil, Polar
import os, sys
from naca_generator import naca4, naca5
from math import cos, factorial
import string

# ---------------------
# Map Design Variables to Discretization
# ---------------------



class GeometrySpline(Component):

    r_af = Array(iotype='in', units='m', desc='locations where airfoils are defined on unit radius')

    idx_cylinder = Int(iotype='in', desc='location where cylinder section ends on unit radius')
    r_max_chord = Float(iotype='in', desc='position of max chord on unit radius')

    Rhub = Float(iotype='in', units='m', desc='blade hub radius')
    Rtip = Float(iotype='in', units='m', desc='blade tip radius')

    chord_sub = Array(iotype='in', units='m', desc='chord at control points')
    theta_sub = Array(iotype='in', units='deg', desc='twist at control points')

    r = Array(iotype='out', units='m', desc='chord at airfoil locations')
    chord = Array(iotype='out', units='m', desc='chord at airfoil locations')
    theta = Array(iotype='out', units='deg', desc='twist at airfoil locations')
    precurve = Array(iotype='out', units='m', desc='precurve at airfoil locations')
    r_af_spacing = Array(iotype='out')  # deprecated: not used anymore


    def execute(self):

        nc = len(self.chord_sub)
        nt = len(self.theta_sub)
        Rhub = self.Rhub
        Rtip = self.Rtip
        idxc = self.idx_cylinder
        r_max_chord = Rhub + (Rtip-Rhub)*self.r_max_chord
        r_cylinder = Rhub + (Rtip-Rhub)*self.r_af[idxc]

        # chord parameterization
        rc_outer, drc_drcmax, drc_drtip = linspace_with_deriv(r_max_chord, Rtip, nc-1)
        r_chord = np.concatenate([[Rhub], rc_outer])
        drc_drcmax = np.concatenate([[0.0], drc_drcmax])
        drc_drtip = np.concatenate([[0.0], drc_drtip])
        drc_drhub = np.concatenate([[1.0], np.zeros(nc-1)])

        # theta parameterization
        r_theta, drt_drcyl, drt_drtip = linspace_with_deriv(r_cylinder, Rtip, nt)

        # spline
        chord_spline = Akima(r_chord, self.chord_sub)
        theta_spline = Akima(r_theta, self.theta_sub)

        self.r = Rhub + (Rtip-Rhub)*self.r_af
        self.chord, dchord_dr, dchord_drchord, dchord_dchordsub = chord_spline.interp(self.r)
        theta_outer, dthetaouter_dr, dthetaouter_drtheta, dthetaouter_dthetasub = theta_spline.interp(self.r[idxc:])

        theta_inner = theta_outer[0] * np.ones(idxc)
        self.theta = np.concatenate([theta_inner, theta_outer])

        self.r_af_spacing = np.diff(self.r_af)

        self.precurve = np.zeros_like(self.chord)  # TODO: for now I'm forcing this to zero, just for backwards compatibility

        # gradients (TODO: rethink these a bit or use Tapenade.)
        n = len(self.r_af)
        dr_draf = (Rtip-Rhub)*np.ones(n)
        dr_dRhub = 1.0 - self.r_af
        dr_dRtip = self.r_af
        dr = hstack([np.diag(dr_draf), np.zeros((n, 1)), dr_dRhub, dr_dRtip, np.zeros((n, nc+nt))])

        dchord_draf = dchord_dr * dr_draf
        dchord_drmaxchord0 = np.dot(dchord_drchord, drc_drcmax)
        dchord_drmaxchord = dchord_drmaxchord0 * (Rtip-Rhub)
        dchord_drhub = np.dot(dchord_drchord, drc_drhub) + dchord_drmaxchord0*(1.0 - self.r_max_chord) + dchord_dr*dr_dRhub
        dchord_drtip = np.dot(dchord_drchord, drc_drtip) + dchord_drmaxchord0*(self.r_max_chord) + dchord_dr*dr_dRtip
        dchord = hstack([np.diag(dchord_draf), dchord_drmaxchord, dchord_drhub, dchord_drtip, dchord_dchordsub, np.zeros((n, nt))])

        dthetaouter_dcyl = np.dot(dthetaouter_drtheta, drt_drcyl)
        dthetaouter_draf = dthetaouter_dr*dr_draf[idxc:]
        dthetaouter_drhub = dthetaouter_dr*dr_dRhub[idxc:]
        dthetaouter_drtip = dthetaouter_dr*dr_dRtip[idxc:] + np.dot(dthetaouter_drtheta, drt_drtip)

        dtheta_draf = np.concatenate([np.zeros(idxc), dthetaouter_draf])
        dtheta_drhub = np.concatenate([dthetaouter_drhub[0]*np.ones(idxc), dthetaouter_drhub])
        dtheta_drtip = np.concatenate([dthetaouter_drtip[0]*np.ones(idxc), dthetaouter_drtip])
        sub = dthetaouter_dthetasub[0, :]
        dtheta_dthetasub = vstack([np.dot(np.ones((idxc, 1)), sub[np.newaxis, :]), dthetaouter_dthetasub])

        dtheta_draf = np.diag(dtheta_draf)
        dtheta_dcyl = np.concatenate([dthetaouter_dcyl[0]*np.ones(idxc), dthetaouter_dcyl])
        dtheta_draf[idxc:, idxc] += dthetaouter_dcyl*(Rtip-Rhub)
        dtheta_drhub += dtheta_dcyl*(1.0 - self.r_af[idxc])
        dtheta_drtip += dtheta_dcyl*self.r_af[idxc]

        dtheta = hstack([dtheta_draf, np.zeros((n, 1)), dtheta_drhub, dtheta_drtip, np.zeros((n, nc)), dtheta_dthetasub])

        drafs_dr = np.zeros((n-1, n))
        for i in range(n-1):
            drafs_dr[i, i] = -1.0
            drafs_dr[i, i+1] = 1.0
        drafs = hstack([drafs_dr, np.zeros((n-1, 3+nc+nt))])

        dprecurve = np.zeros((len(self.precurve), n+3+nc+nt))

        self.J = vstack([dr, dchord, dtheta, drafs, dprecurve])


    def list_deriv_vars(self):

        inputs = ('r_af', 'r_max_chord', 'Rhub', 'Rtip', 'chord_sub', 'theta_sub')
        outputs = ('r', 'chord', 'theta', 'r_af_spacing', 'precurve')

        return inputs, outputs


    def provideJ(self):

        return self.J




# ---------------------
# Default Implementations of Base Classes
# ---------------------


class CCBladeGeometry(GeomtrySetupBase):

    Rtip = Float(iotype='in', units='m', desc='tip radius')
    precurveTip = Float(0.0, iotype='in', units='m', desc='tip radius')
    precone = Float(0.0, iotype='in', desc='precone angle', units='deg')

    def execute(self):

        self.R = self.Rtip*cosd(self.precone) + self.precurveTip*sind(self.precone)


    def list_deriv_vars(self):

        inputs = ('Rtip', 'precurveTip', 'precone')
        outputs = ('R',)

        return inputs, outputs

    def provideJ(self):

        J = np.array([[cosd(self.precone), sind(self.precone),
            (-self.Rtip*sind(self.precone) + self.precurveTip*sind(self.precone))*pi/180.0]])

        return J

class AirfoilParameterization(Component):
    airfoil_files = List(Str, iotype='in', desc='names of airfoil file')
    airfoil_parameterization_type = Enum('Coordinates', ('Coordinates', 'NACA', 'CST'), iotype='in', desc='type of airfoil parameterization, either NACA, CST (Class-Shape-Transformation), or thickness-to-chord-ratio')
    airfoil_analysis_tool = Enum('Files', ('Files', 'XFOIL'), iotype='in', desc='type of airfoil analysis tool, either using XFOIL or files')
    airfoil_parameters = Array(iotype='in', desc='airfoil parameters')
    airfoil_locations = Array(iotype='in', desc='airfoil locations')
    af = Array(iotype='out', desc='CCBlade objects')

    def execute(self):
        if self.airfoil_analysis_tool == 'Files':
            # airfoil files
            n = len(self.airfoil_files)
            af = [0]*n
            afinit = CCAirfoil.initFromAerodynFile

            for i in range(n):
                af[i] = afinit(self.airfoil_files[i])
        else:
            af = self.generate_af()

        self.af = af

    def generate_af(self):

        af_type = self.airfoil_parameterization_type
        af_parameters = self.airfoil_parameters
        if af_type == 'CST':
            n = len(self.airfoil_parameters[0])
            af = [0]*n
        else:
            n = len(self.airfoil_parameters)
            af = [0]*n

        r_over_R = 0.5
        chord_over_r = 0.15
        tsr = 7.55
        cd_max = 1.5

        for i in range(n):
            x = []
            y = []

            if af_type == 'Coordinates':
                try:
                    f = open(af_parameters[i],'r')
                except:
                    print 'There was an error opening the airfoil file %s'%(af_parameters[i])
                    sys.exit(1)
                for line in f:
                    try:
                        x.append(float(string.split(line)[0]))
                        y.append(float(string.split(line)[1]))
                    except:
                        pass
            elif af_type == 'NACA':
                if len(str(int(af_parameters[i]))) == 4:
                    pts = naca4(str(int(af_parameters[i])), 60)
                elif len(str(int(af_parameters[i] == 5))):
                    pts = naca5(str(int(af_parameters[i])), 60)
                else:
                    'Please input only NACA 4 or 5 series'
                for j in range(len(pts)):
                    x.append(pts[j][0])
                    y.append(pts[j][1])
            elif af_type == 'CST':
                n = len(af_parameters)/2
                wu = np.zeros(n)
                wl = np.zeros(n)
                for j in range(n):
                    wu[j] = af_parameters[j][i]
                    wl[j] = af_parameters[j + n][i]
                # wu, wl = np.split(af_parameters[i], 2)
                w1 = np.average(wl)
                w2 = np.average(wu)
                if w1 < w2:
                    pass
                else:
                    higher = wl
                    lower = wu
                    wl = lower
                    wu = higher
                N = 120
                dz = 0.

                # Populate x coordinates
                x = np.ones((N, 1))
                zeta = np.zeros((N, 1))
                for z in range(0, N):
                    zeta[z] = 2 * pi / N * z
                    if z == N - 1:
                        zeta[z] = 2 * pi
                    x[z] = 0.5*(cos(zeta[z])+1)

                # N1 and N2 parameters (N1 = 0.5 and N2 = 1 for airfoil shape)
                N1 = 0.5
                N2 = 1

                try:
                    zerind = np.where(x == 0)  # Used to separate upper and lower surfaces
                    zerind = zerind[0][0]
                except:
                    zerind = N/2

                xl = np.zeros(zerind)
                xu = np.zeros(N-zerind)

                for z in range(len(xl)):
                    xl[z] = np.real(x[z])            # Lower surface x-coordinates
                for z in range(len(xu)):
                    xu[z] = np.real(x[z + zerind])   # Upper surface x-coordinates

                yl = self.__ClassShape(wl, xl, N1, N2, -dz) # Call ClassShape function to determine lower surface y-coordinates
                yu = self.__ClassShape(wu, xu, N1, N2, dz)  # Call ClassShape function to determine upper surface y-coordinates

                y = np.concatenate([yl, yu])  # Combine upper and lower y coordinates
                y = y[::-1]
                # coord_split = [xl, yl, xu, yu]  # Combine x and y into single output
                # coord = [x, y]
                x1 = np.zeros(len(x))
                for k in range(len(x)):
                    x1[k] = x[k][0]
                x = x1

            else:
                print 'Error. Airfoil parameterization type not specified. Please choose Coordinates, NACA, or CST.'

            if i < 3:
                Re1 = [1e6]
                af[0] = CCAirfoil([-180, 0, 180], Re1, [0, 0, 0], [0.5, 0.5, 0.5])
                af[1] = CCAirfoil([-180, 0, 180], Re1, [0, 0, 0], [0.5, 0.5, 0.5])
                af[2] = CCAirfoil([-180, 0, 180], Re1, [0, 0, 0], [0.35, 0.35, 0.35])
            else:
                coordinate_points = [x, y]
                Re = 1e6
                alphas = np.linspace(-20, 20, 80)
                airfoil = pyXLIGHT.xfoilAnalysis(coordinate_points)
                airfoil.re = Re
                airfoil.mach = 0.03
                airfoil.iter = 1000
                cl = np.zeros(len(alphas))
                cd = np.zeros(len(alphas))
                cm = np.zeros(len(alphas))
                for j in range(len(alphas)):
                    angle = alphas[j]
                    cl[j], cd[j], cm[j], lexitflag = airfoil.solveAlpha(angle)
                    # print cl[j], cd[j], angle
                p1 = Polar(Re, alphas, cl, cd, cm)
                af_p = Airfoil([p1])
                af3D = af_p.correction3D(r_over_R, chord_over_r, tsr)
                af_extrap1 = af3D.extrapolate(cd_max)
                alpha_ext, Re_ext, cl_ext, cd_ext, cm_ext = af_extrap1.createDataGrid()
                af[i] = CCAirfoil(alpha_ext, Re_ext, cl_ext, cd_ext)

        return af

    def __ClassShape(self, w, x, N1, N2, dz):

        # Class function; taking input of N1 and N2
        C = np.zeros(len(x), dtype=complex)
        for i in range(len(x)):
            C[i] = x[i]**N1*((1-x[i])**N2)

        # Shape function; using Bernstein Polynomials
        n = len(w) - 1  # Order of Bernstein polynomials

        K = np.zeros(n+1, dtype=complex)
        for i in range(0, n+1):
            K[i] = factorial(n)/(factorial(i)*(factorial((n)-(i))))

        S = np.zeros(len(x), dtype=complex)
        for i in range(len(x)):
            S[i] = 0
            for j in range(0, n+1):
                S[i] += w[j]*K[j]*x[i]**(j) * ((1-x[i])**(n-(j)))

        # Calculate y output
        y = np.zeros(len(x), dtype=complex)
        for i in range(len(y)):
            y[i] = C[i] * S[i] + x[i] * dz

        return y


class CCBlade(AeroBase):
    """blade element momentum code"""

    # (potential) variables
    r = Array(iotype='in', units='m', desc='radial locations where blade is defined (should be increasing and not go all the way to hub or tip)')
    chord = Array(iotype='in', units='m', desc='chord length at each section')
    theta = Array(iotype='in', units='deg', desc='twist angle at each section (positive decreases angle of attack)')
    Rhub = Float(iotype='in', units='m', desc='hub radius')
    Rtip = Float(iotype='in', units='m', desc='tip radius')
    hubHt = Float(iotype='in', units='m', desc='hub height')
    precone = Float(0.0, iotype='in', desc='precone angle', units='deg')
    tilt = Float(0.0, iotype='in', desc='shaft tilt', units='deg')
    yaw = Float(0.0, iotype='in', desc='yaw error', units='deg')

    # TODO: I've not hooked up the gradients for these ones yet.
    precurve = Array(iotype='in', units='m', desc='precurve at each section')
    precurveTip = Float(0.0, iotype='in', units='m', desc='precurve at tip')

    # parameters
    airfoil_files = List(Str, iotype='in', desc='names of airfoil file')
    coordinate_files = List(Str, iotype='in', desc='names of airfoil file')
    B = Int(3, iotype='in', desc='number of blades')
    rho = Float(1.225, iotype='in', units='kg/m**3', desc='density of air')
    mu = Float(1.81206e-5, iotype='in', units='kg/(m*s)', desc='dynamic viscosity of air')
    shearExp = Float(0.2, iotype='in', desc='shear exponent')
    nSector = Int(4, iotype='in', desc='number of sectors to divide rotor face into in computing thrust and power')
    tiploss = Bool(True, iotype='in', desc='include Prandtl tip loss model')
    hubloss = Bool(True, iotype='in', desc='include Prandtl hub loss model')
    wakerotation = Bool(True, iotype='in', desc='include effect of wake rotation (i.e., tangential induction factor is nonzero)')
    usecd = Bool(True, iotype='in', desc='use drag coefficient in computing induction factors')
    af = Array(iotype='in', desc='CCBlade objects')

    missing_deriv_policy = 'assume_zero'

    def execute(self):

        if len(self.precurve) == 0:
            self.precurve = np.zeros_like(self.r)

        af = self.af

        self.ccblade = CCBlade_PY(self.r, self.chord, self.theta, af, self.Rhub, self.Rtip, self.B,
            self.rho, self.mu, self.precone, self.tilt, self.yaw, self.shearExp, self.hubHt,
            self.nSector, self.precurve, self.precurveTip, tiploss=self.tiploss, hubloss=self.hubloss,
            wakerotation=self.wakerotation, usecd=self.usecd, derivatives=True)


        if self.run_case == 'power':

            # power, thrust, torque
            self.P, self.T, self.Q, self.dP, self.dT, self.dQ \
                = self.ccblade.evaluate(self.Uhub, self.Omega, self.pitch, coefficient=False)


        elif self.run_case == 'loads':

            # distributed loads
            Np, Tp, self.dNp, self.dTp \
                = self.ccblade.distributedAeroLoads(self.V_load, self.Omega_load, self.pitch_load, self.azimuth_load)

            # concatenate loads at root/tip
            self.loads.r = np.concatenate([[self.Rhub], self.r, [self.Rtip]])
            Np = np.concatenate([[0.0], Np, [0.0]])
            Tp = np.concatenate([[0.0], Tp, [0.0]])

            # conform to blade-aligned coordinate system
            self.loads.Px = Np
            self.loads.Py = -Tp
            self.loads.Pz = 0*Np

            # return other outputs needed
            self.loads.V = self.V_load
            self.loads.Omega = self.Omega_load
            self.loads.pitch = self.pitch_load
            self.loads.azimuth = self.azimuth_load


    def list_deriv_vars(self):

        if self.run_case == 'power':
            inputs = ('precone', 'tilt', 'hubHt', 'Rhub', 'Rtip', 'yaw',
                'Uhub', 'Omega', 'pitch', 'r', 'chord', 'theta', 'precurve', 'precurveTip')
            outputs = ('P', 'T', 'Q')

        elif self.run_case == 'loads':

            inputs = ('r', 'chord', 'theta', 'Rhub', 'Rtip', 'hubHt', 'precone',
                'tilt', 'yaw', 'V_load', 'Omega_load', 'pitch_load', 'azimuth_load', 'precurve')
            outputs = ('loads.r', 'loads.Px', 'loads.Py', 'loads.Pz', 'loads.V',
                'loads.Omega', 'loads.pitch', 'loads.azimuth')

        return inputs, outputs


    def provideJ(self):

        if self.run_case == 'power':

            dP = self.dP
            dT = self.dT
            dQ = self.dQ

            jP = hstack([dP['dprecone'], dP['dtilt'], dP['dhubHt'], dP['dRhub'], dP['dRtip'],
                dP['dyaw'], dP['dUinf'], dP['dOmega'], dP['dpitch'], dP['dr'], dP['dchord'], dP['dtheta'],
                dP['dprecurve'], dP['dprecurveTip']])
            jT = hstack([dT['dprecone'], dT['dtilt'], dT['dhubHt'], dT['dRhub'], dT['dRtip'],
                dT['dyaw'], dT['dUinf'], dT['dOmega'], dT['dpitch'], dT['dr'], dT['dchord'], dT['dtheta'],
                dT['dprecurve'], dT['dprecurveTip']])
            jQ = hstack([dQ['dprecone'], dQ['dtilt'], dQ['dhubHt'], dQ['dRhub'], dQ['dRtip'],
                dQ['dyaw'], dQ['dUinf'], dQ['dOmega'], dQ['dpitch'], dQ['dr'], dQ['dchord'], dQ['dtheta'],
                dQ['dprecurve'], dQ['dprecurveTip']])

            J = vstack([jP, jT, jQ])


        elif self.run_case == 'loads':

            dNp = self.dNp
            dTp = self.dTp
            n = len(self.r)

            dr_dr = vstack([np.zeros(n), np.eye(n), np.zeros(n)])
            dr_dRhub = np.zeros(n+2)
            dr_dRtip = np.zeros(n+2)
            dr_dRhub[0] = 1.0
            dr_dRtip[-1] = 1.0
            dr = hstack([dr_dr, np.zeros((n+2, 2*n)), dr_dRhub, dr_dRtip, np.zeros((n+2, 8+n))])

            jNp = hstack([dNp['dr'], dNp['dchord'], dNp['dtheta'], dNp['dRhub'], dNp['dRtip'],
                dNp['dhubHt'], dNp['dprecone'], dNp['dtilt'], dNp['dyaw'], dNp['dUinf'],
                dNp['dOmega'], dNp['dpitch'], dNp['dazimuth'], dNp['dprecurve']])
            jTp = hstack([dTp['dr'], dTp['dchord'], dTp['dtheta'], dTp['dRhub'], dTp['dRtip'],
                dTp['dhubHt'], dTp['dprecone'], dTp['dtilt'], dTp['dyaw'], dTp['dUinf'],
                dTp['dOmega'], dTp['dpitch'], dTp['dazimuth'], dTp['dprecurve']])
            dPx = vstack([np.zeros(4*n+10), jNp, np.zeros(4*n+10)])
            dPy = vstack([np.zeros(4*n+10), -jTp, np.zeros(4*n+10)])
            dPz = np.zeros((n+2, 4*n+10))

            dV = np.zeros(4*n+10)
            dV[3*n+6] = 1.0
            dOmega = np.zeros(4*n+10)
            dOmega[3*n+7] = 1.0
            dpitch = np.zeros(4*n+10)
            dpitch[3*n+8] = 1.0
            dazimuth = np.zeros(4*n+10)
            dazimuth[3*n+9] = 1.0

            J = vstack([dr, dPx, dPy, dPz, dV, dOmega, dpitch, dazimuth])


        return J



class CSMDrivetrain(DrivetrainLossesBase):
    """drivetrain losses from NREL cost and scaling model"""

    drivetrainType = Enum('geared', ('geared', 'single_stage', 'multi_drive', 'pm_direct_drive'), iotype='in')

    missing_deriv_policy = 'assume_zero'

    def execute(self):

        drivetrainType = self.drivetrainType
        aeroPower = self.aeroPower
        aeroTorque = self.aeroTorque
        ratedPower = self.ratedPower


        if drivetrainType == 'geared':
            constant = 0.01289
            linear = 0.08510
            quadratic = 0.0

        elif drivetrainType == 'single_stage':
            constant = 0.01331
            linear = 0.03655
            quadratic = 0.06107

        elif drivetrainType == 'multi_drive':
            constant = 0.01547
            linear = 0.04463
            quadratic = 0.05790

        elif drivetrainType == 'pm_direct_drive':
            constant = 0.01007
            linear = 0.02000
            quadratic = 0.06899


        Pbar0 = aeroPower / ratedPower

        # handle negative power case (with absolute value)
        Pbar1, dPbar1_dPbar0 = smooth_abs(Pbar0, dx=0.01)

        # truncate idealized power curve for purposes of efficiency calculation
        Pbar, dPbar_dPbar1, _ = smooth_min(Pbar1, 1.0, pct_offset=0.01)

        # compute efficiency
        eff = 1.0 - (constant/Pbar + linear + quadratic*Pbar)

        self.power = aeroPower * eff

        # gradients
        dPbar_dPa = dPbar_dPbar1*dPbar1_dPbar0/ratedPower
        dPbar_dPr = -dPbar_dPbar1*dPbar1_dPbar0*aeroPower/ratedPower**2

        deff_dPa = dPbar_dPa*(constant/Pbar**2 - quadratic)
        deff_dPr = dPbar_dPr*(constant/Pbar**2 - quadratic)

        dP_dPa = eff + aeroPower*deff_dPa
        dP_dPr = aeroPower*deff_dPr

        self.J = hstack([np.diag(dP_dPa), dP_dPr])


    def list_deriv_vars(self):

        inputs = ('aeroPower', 'ratedPower')
        outputs = ('power',)

        return inputs, outputs

    def provideJ(self):

        return self.J




class WeibullCDF(CDFBase):
    """Weibull cumulative distribution function"""

    A = Float(iotype='in', desc='scale factor')
    k = Float(iotype='in', desc='shape or form factor')

    def execute(self):

        self.F = 1.0 - np.exp(-(self.x/self.A)**self.k)

    def list_deriv_vars(self):
        inputs = ('x',)
        outputs = ('F',)

        return inputs, outputs

    def provideJ(self):

        x = self.x
        A = self.A
        k = self.k
        J = np.diag(np.exp(-(x/A)**k)*(x/A)**(k-1)*k/A)

        return J


class WeibullWithMeanCDF(CDFBase):
    """Weibull cumulative distribution function"""

    xbar = Float(iotype='in', desc='mean value of distribution')
    k = Float(iotype='in', desc='shape or form factor')

    def execute(self):

        A = self.xbar / gamma(1.0 + 1.0/self.k)

        self.F = 1.0 - np.exp(-(self.x/A)**self.k)


    def list_deriv_vars(self):

        inputs = ('x', 'xbar')
        outputs = ('F',)

        return inputs, outputs

    def provideJ(self):

        x = self.x
        k = self.k
        A = self.xbar / gamma(1.0 + 1.0/k)
        dx = np.diag(np.exp(-(x/A)**k)*(x/A)**(k-1)*k/A)
        dxbar = -np.exp(-(x/A)**k)*(x/A)**(k-1)*k*x/A**2/gamma(1.0 + 1.0/k)

        J = hstack([dx, dxbar])

        return J



class RayleighCDF(CDFBase):
    """Rayleigh cumulative distribution function"""

    xbar = Float(iotype='in', desc='mean value of distribution')

    def execute(self):

        self.F = 1.0 - np.exp(-pi/4.0*(self.x/self.xbar)**2)

    def list_deriv_vars(self):

        inputs = ('x', 'xbar')
        outputs = ('F',)

        return inputs, outputs

    def provideJ(self):

        x = self.x
        xbar = self.xbar
        dx = np.diag(np.exp(-pi/4.0*(x/xbar)**2)*pi*x/(2.0*xbar**2))
        dxbar = -np.exp(-pi/4.0*(x/xbar)**2)*pi*x**2/(2.0*xbar**3)
        J = hstack([dx, dxbar])

        return J



def common_io_with_ccblade(assembly, varspeed, varpitch, cdf_type):

    regulated = varspeed or varpitch

    # add inputs
    assembly.add('r_af', Array(iotype='in', units='m', desc='locations where airfoils are defined on unit radius'))
    assembly.add('r_max_chord', Float(iotype='in'))
    assembly.add('chord_sub', Array(iotype='in', units='m', desc='chord at control points'))
    assembly.add('theta_sub', Array(iotype='in', units='deg', desc='twist at control points'))
    assembly.add('Rhub', Float(iotype='in', units='m', desc='hub radius'))
    assembly.add('Rtip', Float(iotype='in', units='m', desc='tip radius'))
    assembly.add('hubHt', Float(iotype='in', units='m'))
    assembly.add('precone', Float(0.0, iotype='in', desc='precone angle', units='deg'))
    assembly.add('tilt', Float(0.0, iotype='in', desc='shaft tilt', units='deg'))
    assembly.add('yaw', Float(0.0, iotype='in', desc='yaw error', units='deg'))
    assembly.add('airfoil_files', List(Str, iotype='in', desc='names of airfoil file'))
    assembly.add('coordinate_files', List(Str, iotype='in', desc='names of airfoil file'))
    assembly.add('idx_cylinder', Int(iotype='in', desc='location where cylinder section ends on unit radius'))
    assembly.add('B', Int(3, iotype='in', desc='number of blades'))
    assembly.add('rho', Float(1.225, iotype='in', units='kg/m**3', desc='density of air'))
    assembly.add('mu', Float(1.81206e-5, iotype='in', units='kg/m/s', desc='dynamic viscosity of air'))
    assembly.add('shearExp', Float(0.2, iotype='in', desc='shear exponent'))
    assembly.add('nSector', Int(4, iotype='in', desc='number of sectors to divide rotor face into in computing thrust and power'))
    assembly.add('tiploss', Bool(True, iotype='in', desc='include Prandtl tip loss model'))
    assembly.add('hubloss', Bool(True, iotype='in', desc='include Prandtl hub loss model'))
    assembly.add('wakerotation', Bool(True, iotype='in', desc='include effect of wake rotation (i.e., tangential induction factor is nonzero)'))
    assembly.add('usecd', Bool(True, iotype='in', desc='use drag coefficient in computing induction factors'))
    assembly.add('npts_coarse_power_curve', Int(20, iotype='in', desc='number of points to evaluate aero analysis at'))
    assembly.add('npts_spline_power_curve', Int(200, iotype='in', desc='number of points to use in fitting spline to power curve'))
    assembly.add('AEP_loss_factor', Float(1.0, iotype='in', desc='availability and other losses (soiling, array, etc.)'))

    if varspeed:
        assembly.add('control', VarTree(VarSpeedMachine(), iotype='in'))
    else:
        assembly.add('control', VarTree(FixedSpeedMachine(), iotype='in'))

    assembly.add('drivetrainType', Enum('geared', ('geared', 'single_stage', 'multi_drive', 'pm_direct_drive'), iotype='in'))
    assembly.add('cdf_mean_wind_speed', Float(iotype='in', units='m/s', desc='mean wind speed of site cumulative distribution function'))

    if cdf_type == 'weibull':
        assembly.add('weibull_shape_factor', Float(iotype='in', desc='(shape factor of weibull distribution)'))

    # outputs
    assembly.add('AEP', Float(iotype='out', units='kW*h', desc='annual energy production'))
    assembly.add('V', Array(iotype='out', units='m/s', desc='wind speeds (power curve)'))
    assembly.add('P', Array(iotype='out', units='W', desc='power (power curve)'))
    assembly.add('diameter', Float(iotype='out', units='m'))
    if regulated:
        assembly.add('ratedConditions', VarTree(RatedConditions(), iotype='out'))



def common_configure_with_ccblade(assembly, varspeed, varpitch, cdf_type):
    common_configure(assembly, varspeed, varpitch)

    # put in parameterization for CCBlade
    assembly.add('spline', GeometrySpline())
    assembly.replace('geom', CCBladeGeometry())
    assembly.replace('analysis', CCBlade())
    assembly.replace('dt', CSMDrivetrain())
    if cdf_type == 'rayleigh':
        assembly.replace('cdf', RayleighCDF())
    elif cdf_type == 'weibull':
        assembly.replace('cdf', WeibullWithMeanCDF())


    # add spline to workflow
    assembly.driver.workflow.add('spline')

    # connections to spline
    assembly.connect('r_af', 'spline.r_af')
    assembly.connect('r_max_chord', 'spline.r_max_chord')
    assembly.connect('chord_sub', 'spline.chord_sub')
    assembly.connect('theta_sub', 'spline.theta_sub')
    assembly.connect('idx_cylinder', 'spline.idx_cylinder')
    assembly.connect('Rhub', 'spline.Rhub')
    assembly.connect('Rtip', 'spline.Rtip')

    # connections to geom
    assembly.connect('Rtip', 'geom.Rtip')
    assembly.connect('precone', 'geom.precone')

    # connections to analysis
    assembly.connect('spline.r', 'analysis.r')
    assembly.connect('spline.chord', 'analysis.chord')
    assembly.connect('spline.theta', 'analysis.theta')
    assembly.connect('spline.precurve', 'analysis.precurve')
    assembly.connect('Rhub', 'analysis.Rhub')
    assembly.connect('Rtip', 'analysis.Rtip')
    assembly.connect('hubHt', 'analysis.hubHt')
    assembly.connect('precone', 'analysis.precone')
    assembly.connect('tilt', 'analysis.tilt')
    assembly.connect('yaw', 'analysis.yaw')
    assembly.connect('airfoil_files', 'analysis.airfoil_files')
    assembly.connect('coordinate_files', 'analysis.coordinate_files')
    assembly.connect('B', 'analysis.B')
    assembly.connect('rho', 'analysis.rho')
    assembly.connect('mu', 'analysis.mu')
    assembly.connect('shearExp', 'analysis.shearExp')
    assembly.connect('nSector', 'analysis.nSector')
    assembly.connect('tiploss', 'analysis.tiploss')
    assembly.connect('hubloss', 'analysis.hubloss')
    assembly.connect('wakerotation', 'analysis.wakerotation')
    assembly.connect('usecd', 'analysis.usecd')

    # connections to dt
    assembly.connect('drivetrainType', 'dt.drivetrainType')
    assembly.dt.missing_deriv_policy = 'assume_zero'  # TODO: openmdao bug remove later

    # connnections to cdf
    assembly.connect('cdf_mean_wind_speed', 'cdf.xbar')
    if cdf_type == 'weibull':
        assembly.connect('weibull_shape_factor', 'cdf.k')



class RotorAeroVSVPWithCCBlade(Assembly):

    def __init__(self, cdf_type='weibull'):
        self.cdf_type = cdf_type
        super(RotorAeroVSVPWithCCBlade, self).__init__()

    def configure(self):
        varspeed = True
        varpitch = True
        common_io_with_ccblade(self, varspeed, varpitch, self.cdf_type)
        common_configure_with_ccblade(self, varspeed, varpitch, self.cdf_type)


class RotorAeroVSFPWithCCBlade(Assembly):

    def __init__(self, cdf_type='weibull'):
        self.cdf_type = cdf_type
        super(RotorAeroVSFPWithCCBlade, self).__init__()

    def configure(self):
        varspeed = True
        varpitch = False
        common_io_with_ccblade(self, varspeed, varpitch, self.cdf_type)
        common_configure_with_ccblade(self, varspeed, varpitch, self.cdf_type)



class RotorAeroFSVPWithCCBlade(Assembly):

    def __init__(self, cdf_type='weibull'):
        self.cdf_type = cdf_type
        super(RotorAeroFSVPWithCCBlade, self).__init__()

    def configure(self):
        varspeed = False
        varpitch = True
        common_io_with_ccblade(self, varspeed, varpitch, self.cdf_type)
        common_configure_with_ccblade(self, varspeed, varpitch, self.cdf_type)



class RotorAeroFSFPWithCCBlade(Assembly):

    def __init__(self, cdf_type='weibull'):
        self.cdf_type = cdf_type
        super(RotorAeroFSFPWithCCBlade, self).__init__()

    def configure(self):
        varspeed = False
        varpitch = False
        common_io_with_ccblade(self, varspeed, varpitch, self.cdf_type)
        common_configure_with_ccblade(self, varspeed, varpitch, self.cdf_type)



if __name__ == '__main__':

    optimize = True

    import os

    # --- instantiate rotor ----
    cdf_type = 'weibull'
    rotor = RotorAeroVSVPWithCCBlade(cdf_type)
    # --------------------------------

    # --- rotor geometry ------------
    rotor.r_max_chord = 0.23577  # (Float): location of second control point (generally also max chord)
    rotor.chord_sub = [3.2612, 4.5709, 3.3178, 1.4621]  # (Array, m): chord at control points
    rotor.theta_sub = [13.2783, 7.46036, 2.89317, -0.0878099]  # (Array, deg): twist at control points
    rotor.Rhub = 1.5  # (Float, m): hub radius
    rotor.Rtip = 63.0  # (Float, m): tip radius
    rotor.precone = 2.5  # (Float, deg): precone angle
    rotor.tilt = -5.0  # (Float, deg): shaft tilt
    rotor.yaw = 0.0  # (Float, deg): yaw error
    rotor.B = 3  # (Int): number of blades
    # -------------------------------------

    # --- airfoils ------------
    basepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), '5MW_AFFiles')

    # load all airfoils
    airfoil_types = [0]*8
    airfoil_types[0] = basepath + os.path.sep + 'Cylinder1.dat'
    airfoil_types[1] = basepath + os.path.sep + 'Cylinder2.dat'
    airfoil_types[2] = basepath + os.path.sep + 'DU40_A17.dat'
    airfoil_types[3] = basepath + os.path.sep + 'DU35_A17.dat'
    airfoil_types[4] = basepath + os.path.sep + 'DU30_A17.dat'
    airfoil_types[5] = basepath + os.path.sep + 'DU25_A17.dat'
    airfoil_types[6] = basepath + os.path.sep + 'DU21_A17.dat'
    airfoil_types[7] = basepath + os.path.sep + 'NACA64_A17.dat'

    # place at appropriate radial stations
    af_idx = [0, 0, 1, 2, 3, 3, 4, 5, 5, 6, 6, 7, 7, 7, 7, 7, 7]

    n = len(af_idx)
    af = [0]*n
    for i in range(n):
        af[i] = airfoil_types[af_idx[i]]

    rotor.airfoil_files = af  # (List): paths to AeroDyn-style airfoil files
    rotor.r_af = np.array([0.02222276, 0.06666667, 0.11111057, 0.16666667, 0.23333333, 0.3, 0.36666667,
        0.43333333, 0.5, 0.56666667, 0.63333333, 0.7, 0.76666667, 0.83333333, 0.88888943,
        0.93333333, 0.97777724])    # (Array, m): locations where airfoils are defined on unit radius
    rotor.idx_cylinder = 3  # (Int): index in r_af where cylinder section ends
    # -------------------------------------

    # --- site characteristics --------
    rotor.rho = 1.225  # (Float, kg/m**3): density of air
    rotor.mu = 1.81206e-5  # (Float, kg/m/s): dynamic viscosity of air
    rotor.shearExp = 0.2  # (Float): shear exponent
    rotor.hubHt = 80.0  # (Float, m)
    rotor.cdf_mean_wind_speed = 6.0  # (Float, m/s): mean wind speed of site cumulative distribution function
    rotor.weibull_shape_factor = 2.0  # (Float): shape factor of weibull distribution
    # -------------------------------------


    # --- control settings ------------
    rotor.control.Vin = 3.0  # (Float, m/s): cut-in wind speed
    rotor.control.Vout = 25.0  # (Float, m/s): cut-out wind speed
    rotor.control.ratedPower = 5e6  # (Float, W): rated power
    rotor.control.pitch = 0.0  # (Float, deg): pitch angle in region 2 (and region 3 for fixed pitch machines)
    rotor.control.minOmega = 0.0  # (Float, rpm): minimum allowed rotor rotation speed
    rotor.control.maxOmega = 12.0  # (Float, rpm): maximum allowed rotor rotation speed
    rotor.control.tsr = 7.55  # **dv** (Float): tip-speed ratio in Region 2 (should be optimized externally)
    # -------------------------------------

    # --- drivetrain model for efficiency --------
    rotor.drivetrainType = 'geared'
    # -------------------------------------


    # --- analysis options ------------
    rotor.nSector = 4  # (Int): number of sectors to divide rotor face into in computing thrust and power
    rotor.npts_coarse_power_curve = 20  # (Int): number of points to evaluate aero analysis at
    rotor.npts_spline_power_curve = 200  # (Int): number of points to use in fitting spline to power curve
    rotor.AEP_loss_factor = 1.0  # (Float): availability and other losses (soiling, array, etc.)
    rotor.tiploss = True  # (Bool): include Prandtl tip loss model
    rotor.hubloss = True  # (Bool): include Prandtl hub loss model
    rotor.wakerotation = True  # (Bool): include effect of wake rotation (i.e., tangential induction factor is nonzero)
    rotor.usecd = True  # (Bool): use drag coefficient in computing induction factors
    # -------------------------------------

    # --- run ------------
    rotor.run()

    AEP0 = rotor.AEP
    print 'AEP0 =', AEP0

    import matplotlib.pyplot as plt
    plt.plot(rotor.V, rotor.P/1e6)
    plt.xlabel('wind speed (m/s)')
    plt.ylabel('power (MW)')
    plt.show()

    # --------------------------


    if optimize:

        # --- optimizer imports ---
        from pyopt_driver.pyopt_driver import pyOptDriver
        from openmdao.lib.casehandlers.api import DumpCaseRecorder
        # ----------------------

        # --- Setup Pptimizer ---
        rotor.replace('driver', pyOptDriver())
        rotor.driver.optimizer = 'SNOPT'
        rotor.driver.options = {'Major feasibility tolerance': 1e-6,
                               'Minor feasibility tolerance': 1e-6,
                               'Major optimality tolerance': 1e-5,
                               'Function precision': 1e-8}
        # ----------------------

        # --- Objective ---
        rotor.driver.add_objective('-aep.AEP/%f' % AEP0)
        # ----------------------

        # --- Design Variables ---
        rotor.driver.add_parameter('r_max_chord', low=0.1, high=0.5)
        rotor.driver.add_parameter('chord_sub', low=0.4, high=5.3)
        rotor.driver.add_parameter('theta_sub', low=-10.0, high=30.0)
        rotor.driver.add_parameter('control.tsr', low=3.0, high=14.0)
        # ----------------------

        # --- recorder ---
        rotor.recorders = [DumpCaseRecorder()]
        # ----------------------

        # --- Constraints ---
        rotor.driver.add_constraint('1.0 >= 0.0')  # dummy constraint, OpenMDAO bug when using pyOpt
        # ----------------------

        # --- run opt ---
        rotor.run()
        # ---------------

