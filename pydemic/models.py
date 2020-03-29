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

import numpy as np
from datetime import datetime, timezone

from pydemic import Reaction, GammaProcess, CompartmentalModelSimulation, date_to_ms


class NeherModelSimulation(CompartmentalModelSimulation):
    """
    Each compartment has n=9 age bins (demographics)
    ["0-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]

    Interactions between compartments are according to equations
    [TODO FIXME src/ref] in the pdf
    and are encapsulated in the reactions definition below.

    TODO Current model does not implement hospital overflow.
    """

    population = 1.e6
    avg_infection_rate = 1.
    peak_day = 15
    seasonal_forcing = 0.

    def beta(self, t, y):
        phase = 2. * np.pi * (t-self.peak_day)/365
        return self.avg_infection_rate * (1. + self.seasonal_forcing * np.cos(phase))

    def __init__(self, epidemiology, severity, imports_per_day,
                 n_age_groups, containment):
        self.containment = lambda t,y: containment(t)

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
                     lambda t, y: ((1. - isolated_frac) * self.beta(t, y) * self.containment(t, y) * y.susceptible
                                   * y.infectious.sum() / self.population)),
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
        N = population.population_served
        n_age_groups = len(age_distribution.counts)
        y0 = {
            'susceptible': np.array([int(np.round(x)) for x in np.array(age_distribution.counts)*N/sum(age_distribution.counts)]),
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

    def __call__(self, t_span, y0, sampler, dt=.01):
        self.population = sum([y0[x].sum() for x in y0])
        t_start = (datetime(*t_span[0]) - datetime(2020, 1, 1)).days
        t_end = (datetime(*t_span[1]) - datetime(2020, 1, 1)).days
        rval = super().__call__([t_start, t_end], y0, sampler, dt=dt)
        return rval



class ExtendedSimulation(CompartmentalModelSimulation):
    def __init__(self, population, avg_infection_rate, *args):
        reactions = (
            Reaction('susceptible', 'exposed',
                     lambda t, y: (avg_infection_rate * y.susceptible
                                   * y.infectious / population)),
            GammaProcess('exposed', 'infectious', shape=3, scale=5),
            Reaction('infectious', 'critical', lambda t, y: 1/5),
            GammaProcess('infectious', 'recovered', shape=4, scale=lambda t, y: 5),
            GammaProcess('infectious', 'dead', shape=3, scale=lambda t, y: 10),
            Reaction('critical', 'dead',
                     lambda t, y: y.critical/y.susceptible/population),
            Reaction('critical', 'recovered', lambda t, y: 1/7),
        )
        super().__init__(reactions)


class SEIRModelSimulation(CompartmentalModelSimulation):
    def __init__(self, avg_infection_rate=10, infectious_rate=5, removal_rate=1,
                 population=None):
        self.avg_infection_rate = avg_infection_rate
        self.population = population

        reactions = (
            Reaction("susceptible", "exposed",
                     lambda t, y: (self.beta(t, y) * y.susceptible
                                   * y.infectious.sum() / self.population)),
            Reaction("exposed", "infectious",
                     lambda t, y: infectious_rate * y.exposed),
            Reaction("infectious", "removed",
                     lambda t, y: removal_rate * y.infectious),
        )
        super().__init__(reactions)

    def beta(self, t, y):
        return self.avg_infection_rate

    def __call__(self, t_span, y0, sampler, dt=.01, **kwargs):
        self.population = sum(y0[x] for x in y0)
        return super().__call__(t_span, y0, sampler, dt=dt, **kwargs)
