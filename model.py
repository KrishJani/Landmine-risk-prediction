import torch
import torch.nn as nn

import numpy as np
from sklearn.base import BaseEstimator

from scipy.optimize import minimize
from utils import sigmoid
import pandas as pd
from torch.optim import Adam
from torch.utils.data import DataLoader
from loss import IRMLoss

class SparseMax(nn.Module):
    def __init__(self):
        super().__init__()
    
    def forward(self, z):
        # z.shape = b * d
        # https://medium.com/deeplearningmadeeasy/sparsemax-from-paper-to-code-351e9b26647b
        sorted, _ = torch.sort(z, dim=-1, descending=True)
        cumsum = sorted.cumsum(dim=-1)
        col_range = torch.arange(1, z.size(-1)+1, device=z.device)
        is_gt = (1 + col_range*sorted) > cumsum
        kz = is_gt.sum(dim=-1, keepdim=True)
        row_range = torch.arange(z.size(0), device=z.device)[..., None]
        tau_z = (cumsum[row_range, kz-1]-1) / kz
        # global attention map
        return torch.mean((z - tau_z).clamp(0), axis=0).repeat((z.shape[0],1))


class MLPOriginal(nn.Module):
    """Original MLP model - preserved for backward compatibility"""
    def __init__(self, in_features, out_features, classifier):
        super(MLPOriginal, self).__init__()
        self.num_features = in_features 
        self.out_features = out_features
        self.classifier = classifier
        self.base = nn.Sequential(nn.Linear(in_features, self.out_features), 
                                   nn.BatchNorm1d(self.out_features),
                                   nn.ReLU())
        def init_weights(m):
            if isinstance(m, nn.Linear):
                torch.nn.init.xavier_uniform_(m.weight)
        
        self.base.apply(init_weights)

        if self.classifier:
            self.fc = nn.Linear(self.out_features, 1)
            self.fc.apply(init_weights)

    def forward(self, x):
        if self.classifier:
            return self.fc(self.base(x))
        else:
            return self.base(x)

# Alias for backward compatibility
MLP = MLPOriginal


class TabCmptOriginal(nn.Module):
    """Original TabCmpt model - preserved for backward compatibility"""
    def __init__(self, num_features, step, prior=-1):
        super(TabCmptOriginal, self).__init__()
        self.out_features = 20 # hidden_layer
        self.step = step # number of MLP blocks

        self.attentive_transformer = nn.Sequential(nn.Linear(num_features, num_features), 
                                                    nn.BatchNorm1d(num_features),
                                                    SparseMax())
        self.fc = nn.Linear(self.out_features, 1)
        self.mlp_steps = nn.ModuleList([MLPOriginal(num_features, self.out_features, False) for _ in range(step)])
        
        def init_weights(m):
            if isinstance(m, nn.Linear):
                torch.nn.init.xavier_uniform_(m.weight)
        
        self.fc.apply(init_weights)
        self.attentive_transformer.apply(init_weights)
        
        # in [-1,1], -1 unselect features, 
        # 1 select mask_1 features
        # 0.5 select all features uniformly
        self.prior = prior
        self.masks = None

    def _generate_masks(self, x):
        masks = []
        acc_mask = None
        for i in range(self.step):
            if i == 0:
                acc_mask = self.attentive_transformer(x)
                masks.append(acc_mask)
            else:
                curr_mask = SparseMax()(self.prior * acc_mask)
                masks.append(curr_mask)
                acc_mask *= curr_mask
        self.masks = masks
        
    def forward(self, x):
        self._generate_masks(x)
        out = torch.sum(torch.stack([self.mlp_steps[i](x*self.masks[i]) for i in range(self.step)], 0), dim=0)
        return self.fc(out) 
    
    def get_importance(self, x):
        etas = [self.mlp_steps[i](x*self.masks[i]).sum().item() for i in range(self.step)]
        numerators = torch.sum(torch.stack([etas[i] * self.masks[i][0] for i in range(self.step)], 0), dim=0)
        denominator = torch.sum(torch.stack([etas[i] * self.masks[i][0] for i in range(self.step)], 0))
        return numerators / denominator

# Alias for backward compatibility
TabCmpt = TabCmptOriginal


class PushedLR(BaseEstimator):
    def __init__(self, X, y, beta_init=None, penalty='l2', 
                 C=0.00012, p=2.0, max_iter=1000):
        self.C = C
        self.penalty = penalty
        self.beta = None
        self.beta_init = beta_init # We can load fitted full LR model
        self.p = p
        self.max_iter = max_iter
        self.X = X 
        self.y = y
            
    def predict(self, X):
        X = np.concatenate([np.ones((X.shape[0],1)),X],axis=1) # first coeff fit intercept
        prediction = np.matmul(X, self.beta)
        return (prediction)
    
    def predict_proba(self, X):
        pos_proba = sigmoid(self.predict(X)).reshape((-1,1))
        return np.concatenate([1-pos_proba, pos_proba],axis=1)
    
    def loss_function(self, out, target):
        tol = 1e-10
        bce = -np.mean(target * np.log(out+tol)+(1-target)*np.log((1-out)+tol))
        pos = out[target == 1]
        neg = out[target == 0] 
        proba_diff = (pos[:,None] - neg[None,:])
        surrogate_loss = np.log(1 + np.exp(-proba_diff))
        pos_sum = np.mean(surrogate_loss, axis=0)**self.p
        neg_sum = np.mean(pos_sum, axis=0)
        rank = neg_sum**(1/self.p)
        return bce+rank
    
    def model_error(self):
        error = self.loss_function(sigmoid(self.predict(self.X)), self.y)
        return error
    
    def l2_regularized_loss(self, beta):
        self.beta = beta
        return self.model_error() + self.C*sum(np.array(self.beta)**2)

    def l1_regularized_loss(self, beta):
        self.beta = beta
        return self.model_error() + 0*sum(np.array(abs(self.beta)))
    
    def fit(self, X, y):        
        # Initialize beta estimates (you may need to normalize
        # your data and choose smarter initialization values
        # depending on the shape of your loss function)
        if type(self.beta_init)==type(None):
            # set beta_init = 1 for every feature
            self.beta_init = np.array([1]*(self.X.shape[1]+1))
        else: 
            # Use provided initial values
            pass
            
        if self.beta!=None and all(self.beta_init == self.beta):
            print("Model already fit once; continuing fit with more itrations.")

        if self.penalty == 'l2':  
            res = minimize(self.l2_regularized_loss, self.beta_init,
                        method='L-BFGS-B', tol=0.0001, options={'maxiter': self.max_iter,
                                                    'iprint':101})
        elif self.penalty == 'l1':
            res = minimize(self.l1_regularized_loss, self.beta_init,
                        method='L-BFGS-B', tol=0.0001, options={'maxiter': self.max_iter,
                                                    'iprint':101})
        self.beta = res.x
        self.beta_init = self.beta


# Simple MLP_IRM model for testing (lightweight alternative to complex models)

class SimpleEvent:
    """Simple Event wrapper for notebook-style usage"""
    def __init__(self, X, y, close_hist_mine):
        """
        Args:
            X: pandas DataFrame or numpy array of features
            y: pandas Series or numpy array of labels
            close_hist_mine: pandas Series or numpy array indicating close historical mines (1 if dist < 0.5, 0 otherwise)
        """
        if isinstance(X, pd.DataFrame):
            self.X = X.values
        else:
            self.X = X
        
        if isinstance(y, pd.Series):
            self.y = y.values
        else:
            self.y = y
            
        if isinstance(close_hist_mine, pd.Series):
            self.close_hist_mine = close_hist_mine.values
        else:
            self.close_hist_mine = close_hist_mine
        
        self.X = torch.tensor(self.X, dtype=torch.float32)
        self.y = torch.tensor(self.y, dtype=torch.float32)
        self.close_hist_mine = torch.tensor(self.close_hist_mine, dtype=torch.float32)


class MLP_IRM(nn.Module):
    """Simple MLP with IRM loss - lightweight model for testing"""
    def __init__(self, num_features, hidden_dim=64):
        super(MLP_IRM, self).__init__()
        self.num_features = num_features
        self.hidden_dim = hidden_dim
        
        self.network = nn.Sequential(
            nn.Linear(num_features, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )
        
        # Initialize weights
        def init_weights(m):
            if isinstance(m, nn.Linear):
                torch.nn.init.xavier_uniform_(m.weight)
        
        self.network.apply(init_weights)
    
    def forward(self, x):
        return self.network(x).squeeze(-1)


class MLP_IRM_Estimator:
    """Sklearn-like interface for MLP_IRM model"""
    def __init__(self, num_features, hidden_dim=64, lr=0.001, epochs=100, batch_size=256, device=None):
        self.num_features = num_features
        self.hidden_dim = hidden_dim
        self.lr = lr
        self.epochs = epochs
        self.batch_size = batch_size
        
        if device is None:
            self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        else:
            self.device = device
        
        self.model = MLP_IRM(num_features, hidden_dim).to(self.device)
        self.optimizer = Adam(self.model.parameters(), lr=lr)
        self.irm_loss = IRMLoss()
        self.is_fitted = False
    
    def fit(self, train_data, val_data=None):
        """
        Train the model using IRM loss
        
        Args:
            train_data: SimpleEvent object with X, y, close_hist_mine
            val_data: Optional SimpleEvent object for validation
        """
        self.model.train()
        
        # Create data loaders
        train_dataset = torch.utils.data.TensorDataset(
            train_data.X, train_data.y, train_data.close_hist_mine
        )
        train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)
        
        for epoch in range(self.epochs):
            total_loss = 0.0
            num_batches = 0
            
            for batch_X, batch_y, batch_hist_mine in train_loader:
                batch_X = batch_X.to(self.device)
                batch_y = batch_y.to(self.device)
                batch_hist_mine = batch_hist_mine.to(self.device)
                
                self.optimizer.zero_grad()
                
                # Forward pass
                logits = self.model(batch_X)
                
                # Compute IRM loss
                loss = self.irm_loss(self.model, batch_hist_mine, batch_X, batch_y)
                
                # Backward pass
                loss.backward()
                self.optimizer.step()
                
                total_loss += loss.item()
                num_batches += 1
            
            if (epoch + 1) % 10 == 0:
                avg_loss = total_loss / num_batches if num_batches > 0 else 0
                print(f"Epoch {epoch + 1}/{self.epochs}, Loss: {avg_loss:.4f}")
        
        self.is_fitted = True
        return self
    
    def predict_proba(self, test_data):
        """
        Predict probabilities for test data
        
        Args:
            test_data: SimpleEvent object with X (y and close_hist_mine can be dummy values)
        
        Returns:
            numpy array of probabilities (positive class)
        """
        self.model.eval()
        
        test_dataset = torch.utils.data.TensorDataset(
            test_data.X, test_data.y, test_data.close_hist_mine
        )
        test_loader = DataLoader(test_dataset, batch_size=self.batch_size, shuffle=False)
        
        all_probs = []
        
        with torch.no_grad():
            for batch_X, _, _ in test_loader:
                batch_X = batch_X.to(self.device)
                logits = self.model(batch_X)
                probs = torch.sigmoid(logits)
                all_probs.extend(probs.cpu().numpy())
        
        return np.array(all_probs)
    
    def predict(self, test_data):
        """Predict binary labels"""
        probs = self.predict_proba(test_data)
        return (probs > 0.5).astype(int)
