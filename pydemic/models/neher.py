__copyright__ = """
Copyright (C) 2020 George N Wong
Copyright (C) 2020 Zachary J Weiner
"""

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

from datetime import datetime, timedelta
import numpy as np
from pydemic import Reaction, Simulation
from pydemic.models import LikelihoodEstimatorBase


class NeherModelSimulation(Simulation):
    """
    Each compartment has n=9 age bins (demographics)
    ["0-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]

    Interactions between compartments are according to equations
    [TODO FIXME src/ref] in the pdf
    and are encapsulated in the reactions definition below.

    TODO Current model does not implement hospital overflow.
    """

    def beta(self, t, y):
        phase = 2. * np.pi * (t-self.peak_day)/365
        return self.avg_infection_rate * (1. + self.seasonal_forcing * np.cos(phase))

    def __init__(self, epidemiology, severity, imports_per_day,
                 n_age_groups, containment):
        self.containment = lambda t, y: containment(t)

        # translate from epidemiology/severity models into rates
        dHospital = severity.severe/100. * severity.confirmed/100.
        dCritical = severity.critical/100.
        dFatal = severity.fatal/100.

        isolated_frac = severity.isolated / 100
        exposed_infectious_rate = 1. / epidemiology.incubation_time
        infectious_hospitalized_rate = dHospital / epidemiology.infectious_period
        infectious_recovered_rate = (1.-dHospital) / epidemiology.infectious_period
        hospitalized_discharged_rate = (
            (1 - dCritical) / epidemiology.length_hospital_stay
        )
        hospitalized_critical_rate = dCritical / epidemiology.length_hospital_stay
        critical_hospitalized_rate = (1 - dFatal) / epidemiology.length_ICU_stay
        critical_dead_rate = dFatal / epidemiology.length_ICU_stay

        self.avg_infection_rate = epidemiology.r0 / epidemiology.infectious_period
        self.seasonal_forcing = epidemiology.seasonal_forcing
        self.peak_day = 30 * epidemiology.peak_month + 14.75

        reactions = (
            Reaction("susceptible", "exposed",
                     lambda t, y: ((1 - isolated_frac) * self.containment(t, y)
                                   * self.beta(t, y) * y.susceptible
                                   * y.infectious.sum() / y.sum())),
            Reaction("susceptible", "exposed",
                     lambda t, y: imports_per_day / n_age_groups),
            Reaction("exposed", "infectious",
                     lambda t, y: y.exposed * exposed_infectious_rate),
            Reaction("infectious", "hospitalized",
                     lambda t, y: y.infectious * infectious_hospitalized_rate),
            Reaction("infectious", "recovered",
                     lambda t, y: y.infectious * infectious_recovered_rate),
            Reaction("hospitalized", "recovered",
                     lambda t, y: y.hospitalized * hospitalized_discharged_rate),
            Reaction("hospitalized", "critical",
                     lambda t, y: y.hospitalized * hospitalized_critical_rate),
            Reaction("critical", "hospitalized",
                     lambda t, y: y.critical * critical_hospitalized_rate),
            Reaction("critical", "dead",
                     lambda t, y: y.critical * critical_dead_rate)
        )
        super().__init__(reactions)

    def get_initial_population(self, population, age_distribution):
        # FIXME: remove this method?
        N = population.population_served
        n_age_groups = len(age_distribution.counts)
        age_counts = age_distribution.counts
        y0 = {
            'susceptible': np.round(np.array(age_counts) * N / np.sum(age_counts)),
            'exposed': np.zeros(n_age_groups),
            'infectious': np.zeros(n_age_groups),
            'recovered': np.zeros(n_age_groups),
            'hospitalized': np.zeros(n_age_groups),
            'critical': np.zeros(n_age_groups),
            'dead': np.zeros(n_age_groups)
        }
        i_middle = round(n_age_groups / 2) + 1
        y0['susceptible'][i_middle] -= population.suspected_cases_today
        y0['exposed'][i_middle] += population.suspected_cases_today * 0.7
        y0['infectious'][i_middle] += population.suspected_cases_today * 0.3
        return y0

    def get_days_float(self, time_tuple):
        t_diff = datetime(*time_tuple) - datetime(2020, 1, 1)
        return t_diff.total_seconds() / timedelta(days=1).total_seconds()

    def __call__(self, t_span, y0, dt=.01, **kwargs):
        t_start = self.get_days_float(t_span[0])
        t_end = self.get_days_float(t_span[1])
        return super().__call__([t_start, t_end], y0, dt=dt, **kwargs)

    def solve_deterministic(self, t_span, y0, **kwargs):
        t_start = self.get_days_float(t_span[0])
        t_end = self.get_days_float(t_span[1])
        return super().solve_deterministic([t_start, t_end], y0, **kwargs)


class NeherModelEstimator(LikelihoodEstimatorBase):
    def __call__(self, theta):
        fit_values = dict(zip(self.fit_priors.keys(), theta))
        for name, value in fit_values.items():
            prior = self.fit_priors[name]
            if not prior[0] < value < prior[1]:
                return -np.inf

        model_data = self.get_model_data(
            self.data['t'], **fit_values, **self.fixed_parameters
        )

        likelihood = -1/2 * self.norm(model_data.y['dead'].sum(axis=-1),
                                      self.data['dead'])
        return likelihood

    def get_model_data(self, t, **kwargs):
        start_date = datetime(2020, 1, 1) + timedelta(kwargs.pop('start_day'))
        end_date = datetime(2020, 1, 1) + timedelta(kwargs.pop('end_day'))
        start_date = (2020, start_date.month, start_date.day,
                      start_date.hour, start_date.minute, start_date.second)
        end_date = (2020, end_date.month, end_date.day,
                    end_date.hour, end_date.minute, end_date.second)

        from pydemic.load import (get_country_population_model,
                                  get_age_distribution_model)
        country = kwargs.get('country')
        subregion = kwargs.get('subregion', country)
        population = get_country_population_model(country)
        from pydemic import PopulationModel
        population = PopulationModel(
            country='United States of America',
            cases='USA-Illinois',
            population_served=12659682,
            suspected_cases_today=10,  # original 215
            ICU_beds=1e10,  # originally 1055
            hospital_beds=1e10,  # originally 31649
            imports_per_day=1.1   # originally 5.0
        )
        age_distribution = get_age_distribution_model(subregion)
        n_age_groups = len(age_distribution.counts)

        from pydemic import SeverityModel, EpidemiologyModel, ContainmentModel
        severity = SeverityModel(
            id=np.array([0, 2, 4, 6, 8, 10, 12, 14, 16]),
            age_group=np.arange(0., 90., 10),
            isolated=np.array([0., 0., 0., 0., 0., 0., 0., 0., 0.]),
            confirmed=np.array([5., 5., 10., 15., 20., 25., 30., 40., 50.]),
            severe=np.array([1., 3., 3., 3., 6., 10., 25., 35., 50.]),
            critical=np.array([5., 10., 10., 15., 20., 25., 35., 45., 55.]),
            fatal=np.array([30., 30., 30., 30., 30., 40., 40., 50., 50.]),
        )
        epidemiology = EpidemiologyModel(
            r0=kwargs.get('r0'),
            incubation_time=1,
            infectious_period=5,
            length_hospital_stay=7,
            length_ICU_stay=7,
            seasonal_forcing=0.2,
            peak_month=0,
            overflow_severity=2
        )

        mitigation_day = kwargs.pop('mitigation_day')
        cdate = datetime(2020, 1, 1) + timedelta(days=mitigation_day)
        mitigation_date = (cdate.year, cdate.month, cdate.day)
        mitigation_factor = kwargs.pop('mitigation_factor')
        mitigation_width = kwargs.pop('mitigation_width')

        containment = ContainmentModel((2019, 1, 1), (2020, 12, 1))
        containment.add_sharp_event(mitigation_date, mitigation_factor,
                                    dt_days=mitigation_width)

        from pydemic.models import NeherModelSimulation
        sim = NeherModelSimulation(
            epidemiology, severity, population.imports_per_day,
            n_age_groups, containment
        )
        y0 = sim.get_initial_population(population, age_distribution)

        result = sim.solve_deterministic((start_date, end_date), y0)
        return sim.dense_to_logger(result, t)