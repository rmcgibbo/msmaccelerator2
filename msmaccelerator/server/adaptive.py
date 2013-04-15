from mdtraj import trajectory

class AdaptiveSampler(object):
    def __init__(self):
        self._model = pass

    def set_model(self):
        self._model = model

    def choose_structure(self):
        weights = self._model.populations
        state_index = np.where(np.random.multinomial(1, weights) == 1)[0][0]
        
        return self._model.generators[state_index]
        
        