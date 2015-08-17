__author__ = 'ryanbarr'

# === import and instantiate ===
import os
import matplotlib.pyplot as plt
from precomp import Profile, Orthotropic2DMaterial, CompositeSection
import numpy as np
from rotor import RotorSE # (include this line)

rotor = RotorSE()
# -------------------

# === blade grid ===
rotor.initial_aero_grid = np.array([0.02222276, 0.06666667, 0.11111057, 0.16666667, 0.23333333, 0.3, 0.36666667,
    0.43333333, 0.5, 0.56666667, 0.63333333, 0.7, 0.76666667, 0.83333333, 0.88888943, 0.93333333,
    0.97777724])  # (Array): initial aerodynamic grid on unit radius
rotor.initial_str_grid = np.array([0.0, 0.00492790457512, 0.00652942887106, 0.00813095316699, 0.00983257273154,
    0.0114340970275, 0.0130356213234, 0.02222276, 0.024446481932, 0.026048006228, 0.06666667, 0.089508406455,
    0.11111057, 0.146462614229, 0.16666667, 0.195309105255, 0.23333333, 0.276686558545, 0.3, 0.333640766319,
    0.36666667, 0.400404310407, 0.43333333, 0.5, 0.520818918408, 0.56666667, 0.602196371696, 0.63333333,
    0.667358391486, 0.683573824984, 0.7, 0.73242031601, 0.76666667, 0.83333333, 0.88888943, 0.93333333, 0.97777724,
    1.0])  # (Array): initial structural grid on unit radius
rotor.idx_cylinder_aero = 3  # (Int): first idx in r_aero_unit of non-cylindrical section, constant twist inboard of here
rotor.idx_cylinder_str = 14  # (Int): first idx in r_str_unit of non-cylindrical section
rotor.hubFraction = 0.025  # (Float): hub location as fraction of radius
# ------------------

# === blade geometry ===
rotor.r_aero = np.array([0.02222276, 0.06666667, 0.11111057, 0.2, 0.23333333, 0.3, 0.36666667, 0.43333333,
    0.5, 0.56666667, 0.63333333, 0.64, 0.7, 0.83333333, 0.88888943, 0.93333333,
    0.97777724])  # (Array): new aerodynamic grid on unit radius
rotor.r_max_chord = 0.23577  # (Float): location of max chord on unit radius
rotor.chord_sub = [3.2612, 4.5709, 3.3178, 1.4621]  # (Array, m): chord at control points. defined at hub, then at linearly spaced locations from r_max_chord to tip
rotor.theta_sub = [13.2783, 7.46036, 2.89317, -0.0878099]  # (Array, deg): twist at control points.  defined at linearly spaced locations from r[idx_cylinder] to tip
rotor.precurve_sub = [0.0, 0.0, 0.0]  # (Array, m): precurve at control points.  defined at same locations at chord, starting at 2nd control point (root must be zero precurve)
rotor.delta_precurve_sub = [0.0, 0.0, 0.0]  # (Array, m): adjustment to precurve to account for curvature from loading
rotor.sparT = [0.05, 0.047754, 0.045376, 0.031085, 0.0061398]  # (Array, m): spar cap thickness parameters
rotor.teT = [0.1, 0.09569, 0.06569, 0.02569, 0.00569]  # (Array, m): trailing-edge thickness parameters
rotor.bladeLength = 61.5  # (Float, m): blade length (if not precurved or swept) otherwise length of blade before curvature
rotor.delta_bladeLength = 0.0  # (Float, m): adjustment to blade length to account for curvature from loading
rotor.precone = 2.5  # (Float, deg): precone angle
rotor.tilt = 5.0  # (Float, deg): shaft tilt
rotor.yaw = 0.0  # (Float, deg): yaw error
rotor.nBlades = 3  # (Int): number of blades
# ------------------

# === airfoil files ===
basepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), '5MW_AFFiles')

# === airfoil analysis tool ===
rotor.airfoil_analysis_tool = 'XFOIL'  # (Enum): airfoil analysis tool ('Files', 'XFOIL')
airfoil_types = ['0']*8
coordinate_files = ['0']*7

# if using AeroDyn Files to provide aerodynamic data then load all airfoils
airfoil_types[0] = os.path.join(basepath, 'Cylinder1.dat')
airfoil_types[1] = os.path.join(basepath, 'Cylinder2.dat')
airfoil_types[2] = os.path.join(basepath, 'DU40_A17.dat')
airfoil_types[3] = os.path.join(basepath, 'DU35_A17.dat')
airfoil_types[4] = os.path.join(basepath, 'DU30_A17.dat')
airfoil_types[5] = os.path.join(basepath, 'DU25_A17.dat')
airfoil_types[6] = os.path.join(basepath, 'DU21_A17.dat')
airfoil_types[7] = os.path.join(basepath, 'NACA64_A17.dat')

# place at appropriate radial stations
af_idx = [0, 0, 1, 2, 3, 3, 4, 5, 5, 6, 6, 7, 7, 7, 7, 7, 7]

n = len(af_idx)
af = [0]*n
for i in range(n):
    af[i] = airfoil_types[af_idx[i]]
rotor.airfoil_files = af  # (List): names of airfoil file

# === airfoil parameterization  ===
rotor.airfoil_parameterization_type = 'CST'  # (Enum): airfoil parameterization type ('Coordinates', 'NACA', 'CST')

if rotor.airfoil_analysis_tool == 'XFOIL':
    if rotor.airfoil_parameterization_type == 'Coordinates':
        # if using XFOIL to provide aerodynamic data then load airfoil coordinate files
        coordinate_files[0] = os.path.join(basepath, 'Cylinder.pfl')
        coordinate_files[1] = os.path.join(basepath, 'DU40_A17.pfl')
        coordinate_files[2] = os.path.join(basepath, 'DU35_A17.pfl')
        coordinate_files[3] = os.path.join(basepath, 'DU30_A17.pfl')
        coordinate_files[4] = os.path.join(basepath, 'DU25_A17.pfl')
        coordinate_files[5] = os.path.join(basepath, 'DU21_A17.pfl')
        coordinate_files[6] = os.path.join(basepath, 'NACA64_A17.pfl')
        rotor.coordinate_files = coordinate_files

        # place at appropriate radial stations
        coordinate_idx = [0, 0, 0, 1, 2, 2, 3, 4, 4, 5, 5, 6, 6, 6, 6, 6, 6]

        n = len(coordinate_idx)
        af_coordinates = [0]*n
        for i in range(n):
            af_coordinates[i] = coordinate_files[coordinate_idx[i]]
        rotor.airfoil_parameters = af_coordinates  # (List): names of airfoil file

    elif rotor.airfoil_parameterization_type == 'NACA':
        rotor.airfoil_parameters = [2340, 2330, 2325, 2320, 2315, 2310]  # For NACA airfoil parameterization

    elif rotor.airfoil_parameterization_type == 'CST':
        rotor.airfoil_parameters = [[0.7, 0.6, 0.5, -0.3, -0.35, -0.3],  # For CST airfoil parameterization
                                    [0.7, 0.6, 0.5, -0.3, -0.35, -0.3],
                                    [0.7, 0.6, 0.5, -0.3, -0.35, -0.3],
                                    [0.7, 0.6, 0.5, -0.3, -0.35, -0.3],
                                    [0.7, 0.6, 0.5, -0.3, -0.35, -0.3],
                                    [0.7, 0.6, 0.5, -0.3, -0.35, -0.3]]
    else:
        print 'Please specify airfoil parameterization'

rotor.airfoil_locations = [0.1666, 0.36666667, 0.5, 0.63333333, 0.83333333, 0.97777724] # (Array): initial airfoil shape locations on unit radius

# ----------------------

# === atmosphere ===
rotor.rho = 1.225  # (Float, kg/m**3): density of air
rotor.mu = 1.81206e-5  # (Float, kg/m/s): dynamic viscosity of air
rotor.shearExp = 0.25  # (Float): shear exponent
rotor.hubHt = 90.0  # (Float, m): hub height
rotor.turbine_class = 'I'  # (Enum): IEC turbine class
rotor.turbulence_class = 'B'  # (Enum): IEC turbulence class class
rotor.cdf_reference_height_wind_speed = 90.0  # (Float): reference hub height for IEC wind speed (used in CDF calculation)
rotor.g = 9.81  # (Float, m/s**2): acceleration of gravity
# ----------------------

# === control ===
rotor.control.Vin = 3.0  # (Float, m/s): cut-in wind speed
rotor.control.Vout = 25.0  # (Float, m/s): cut-out wind speed
rotor.control.ratedPower = 5e6  # (Float, W): rated power
rotor.control.minOmega = 0.0  # (Float, rpm): minimum allowed rotor rotation speed
rotor.control.maxOmega = 12.0  # (Float, rpm): maximum allowed rotor rotation speed
rotor.control.tsr = 7.55  # (Float): tip-speed ratio in Region 2 (should be optimized externally)
rotor.control.pitch = 0.0  # (Float, deg): pitch angle in region 2 (and region 3 for fixed pitch machines)
rotor.pitch_extreme = 0.0  # (Float, deg): worst-case pitch at survival wind condition
rotor.azimuth_extreme = 0.0  # (Float, deg): worst-case azimuth at survival wind condition
rotor.VfactorPC = 0.7  # (Float): fraction of rated speed at which the deflection is assumed to representative throughout the power curve calculation
# ----------------------

# === aero and structural analysis options ===
rotor.nSector = 4  # (Int): number of sectors to divide rotor face into in computing thrust and power
rotor.npts_coarse_power_curve = 20  # (Int): number of points to evaluate aero analysis at
rotor.npts_spline_power_curve = 200  # (Int): number of points to use in fitting spline to power curve
rotor.AEP_loss_factor = 1.0  # (Float): availability and other losses (soiling, array, etc.)
rotor.drivetrainType = 'geared'  # (Enum)
rotor.nF = 5  # (Int): number of natural frequencies to compute
rotor.dynamic_amplication_tip_deflection = 1.35  # (Float): a dynamic amplification factor to adjust the static deflection calculation
# ----------------------

# === materials and composite layup  ===
basepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), '5MW_PrecompFiles')

materials = Orthotropic2DMaterial.listFromPreCompFile(os.path.join(basepath, 'materials.inp'))

ncomp = len(rotor.initial_str_grid)
upper = [0]*ncomp
lower = [0]*ncomp
webs = [0]*ncomp
profile = [0]*ncomp

rotor.leLoc = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.498, 0.497, 0.465, 0.447, 0.43, 0.411,
    0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4,
    0.4, 0.4, 0.4, 0.4])    # (Array): array of leading-edge positions from a reference blade axis (usually blade pitch axis). locations are normalized by the local chord length. e.g. leLoc[i] = 0.2 means leading edge is 0.2*chord[i] from reference axis.  positive in -x direction for airfoil-aligned coordinate system
rotor.sector_idx_strain_spar = [2]*ncomp  # (Array): index of sector for spar (PreComp definition of sector)
rotor.sector_idx_strain_te = [3]*ncomp  # (Array): index of sector for trailing-edge (PreComp definition of sector)
web1 = np.array([-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 0.4114, 0.4102, 0.4094, 0.3876, 0.3755, 0.3639, 0.345, 0.3342, 0.3313, 0.3274, 0.323, 0.3206, 0.3172, 0.3138, 0.3104, 0.307, 0.3003, 0.2982, 0.2935, 0.2899, 0.2867, 0.2833, 0.2817, 0.2799, 0.2767, 0.2731, 0.2664, 0.2607, 0.2562, 0.1886, -1.0])
web2 = np.array([-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 0.5886, 0.5868, 0.5854, 0.5508, 0.5315, 0.5131, 0.4831, 0.4658, 0.4687, 0.4726, 0.477, 0.4794, 0.4828, 0.4862, 0.4896, 0.493, 0.4997, 0.5018, 0.5065, 0.5101, 0.5133, 0.5167, 0.5183, 0.5201, 0.5233, 0.5269, 0.5336, 0.5393, 0.5438, 0.6114, -1.0])
web3 = np.array([-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
rotor.chord_str_ref = np.array([3.2612, 3.3100915356, 3.32587052924, 3.34159388653, 3.35823798667, 3.37384375335,
    3.38939112914, 3.4774055542, 3.49839685, 3.51343645709, 3.87017220335, 4.04645623801, 4.19408216643,
     4.47641008477, 4.55844487985, 4.57383098262, 4.57285771934, 4.51914315648, 4.47677655262, 4.40075650022,
     4.31069949379, 4.20483735936, 4.08985563932, 3.82931757126, 3.74220276467, 3.54415796922, 3.38732428502,
     3.24931446473, 3.23421422609, 3.22701537997, 3.21972125648, 3.08979310611, 2.95152261813, 2.330753331,
     2.05553464181, 1.82577817774, 1.5860853279, 1.4621])  # (Array, m): chord distribution for reference section, thickness of structural layup scaled with reference thickness (fixed t/c for this case)

for i in range(ncomp):

    webLoc = []
    if web1[i] != -1:
        webLoc.append(web1[i])
    if web2[i] != -1:
        webLoc.append(web2[i])
    if web3[i] != -1:
        webLoc.append(web3[i])

    upper[i], lower[i], webs[i] = CompositeSection.initFromPreCompLayupFile(os.path.join(basepath, 'layup_' + str(i+1) + '.inp'), webLoc, materials)
    profile[i] = Profile.initFromPreCompFile(os.path.join(basepath, 'shape_' + str(i+1) + '.inp'))

rotor.materials = materials  # (List): list of all Orthotropic2DMaterial objects used in defining the geometry
rotor.upperCS = upper  # (List): list of CompositeSection objections defining the properties for upper surface
rotor.lowerCS = lower  # (List): list of CompositeSection objections defining the properties for lower surface
rotor.websCS = webs  # (List): list of CompositeSection objections defining the properties for shear webs
rotor.profile = profile  # (List): airfoil shape at each radial position
# --------------------------------------


# === fatigue ===
rotor.rstar_damage = np.array([0.000, 0.022, 0.067, 0.111, 0.167, 0.233, 0.300, 0.367, 0.433, 0.500,
    0.567, 0.633, 0.700, 0.767, 0.833, 0.889, 0.933, 0.978])  # (Array): nondimensional radial locations of damage equivalent moments
rotor.Mxb_damage = 1e3*np.array([2.3743E+003, 2.0834E+003, 1.8108E+003, 1.5705E+003, 1.3104E+003,
    1.0488E+003, 8.2367E+002, 6.3407E+002, 4.7727E+002, 3.4804E+002, 2.4458E+002, 1.6339E+002,
    1.0252E+002, 5.7842E+001, 2.7349E+001, 1.1262E+001, 3.8549E+000, 4.4738E-001])  # (Array, N*m): damage equivalent moments about blade c.s. x-direction
rotor.Myb_damage = 1e3*np.array([2.7732E+003, 2.8155E+003, 2.6004E+003, 2.3933E+003, 2.1371E+003,
    1.8459E+003, 1.5582E+003, 1.2896E+003, 1.0427E+003, 8.2015E+002, 6.2449E+002, 4.5229E+002,
    3.0658E+002, 1.8746E+002, 9.6475E+001, 4.2677E+001, 1.5409E+001, 1.8426E+000])  # (Array, N*m): damage equivalent moments about blade c.s. y-direction
rotor.strain_ult_spar = 1.0e-2  # (Float): ultimate strain in spar cap
rotor.strain_ult_te = 2500*1e-6 * 2   # (Float): uptimate strain in trailing-edge panels, note that I am putting a factor of two for the damage part only.
rotor.eta_damage = 1.35*1.3*1.0  # (Float): safety factor for fatigue
rotor.m_damage = 10.0  # (Float): slope of S-N curve for fatigue analysis
rotor.N_damage = 365*24*3600*20.0  # (Float): number of cycles used in fatigue analysis  TODO: make function of rotation speed
# ----------------

# from myutilities import plt

# === run and outputs ===
rotor.run()

print 'AEP =', rotor.AEP
print 'diameter =', rotor.diameter
print 'ratedConditions.V =', rotor.ratedConditions.V
print 'ratedConditions.Omega =', rotor.ratedConditions.Omega
print 'ratedConditions.pitch =', rotor.ratedConditions.pitch
print 'ratedConditions.T =', rotor.ratedConditions.T
print 'ratedConditions.Q =', rotor.ratedConditions.Q
print 'mass_one_blade =', rotor.mass_one_blade
print 'mass_all_blades =', rotor.mass_all_blades
print 'I_all_blades =', rotor.I_all_blades
print 'freq =', rotor.freq
print 'tip_deflection =', rotor.tip_deflection
print 'root_bending_moment =', rotor.root_bending_moment
print 'totalCone =', rotor.TotalCone

plt.figure()
plt.plot(rotor.V, rotor.P/1e6)
plt.xlabel('wind speed (m/s)')
plt.xlabel('power (W)')

plt.figure()
plt.plot(rotor.spline.r_str, rotor.strainU_spar, label='suction')
plt.plot(rotor.spline.r_str, rotor.strainL_spar, label='pressure')
plt.plot(rotor.spline.r_str, rotor.eps_crit_spar, label='critical')
plt.ylim([-5e-3, 5e-3])
plt.xlabel('r')
plt.ylabel('strain')
plt.legend()
# plt.save('/Users/sning/Desktop/strain_spar.pdf')
# plt.save('/Users/sning/Desktop/strain_spar.png')

plt.figure()
plt.plot(rotor.spline.r_str, rotor.strainU_te, label='suction')
plt.plot(rotor.spline.r_str, rotor.strainL_te, label='pressure')
plt.plot(rotor.spline.r_str, rotor.eps_crit_te, label='critical')
plt.ylim([-5e-3, 5e-3])
plt.xlabel('r')
plt.ylabel('strain')
plt.legend()
# plt.save('/Users/sning/Desktop/strain_te.pdf')
# plt.save('/Users/sning/Desktop/strain_te.png')

plt.show()
# ----------------