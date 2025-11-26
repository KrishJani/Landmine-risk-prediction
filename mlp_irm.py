"""
Simple MLP_IRM model for testing - lightweight alternative to complex models
This module provides a simple interface matching the notebook usage pattern.
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from torch.optim import Adam
from torch.utils.data import DataLoader
from loss import IRMLoss


class Event:
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


class MLP_IRM_Network(nn.Module):
    """Simple MLP network with IRM loss - lightweight model for testing"""
    def __init__(self, num_features, hidden_dim=64):
        super(MLP_IRM_Network, self).__init__()
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


class MLP_IRM:
    """Sklearn-like interface for MLP_IRM model matching notebook usage"""
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
        
        self.model = MLP_IRM_Network(num_features, hidden_dim).to(self.device)
        self.optimizer = Adam(self.model.parameters(), lr=lr)
        self.irm_loss = IRMLoss()
        self.is_fitted = False
    
    def fit(self, train_data, val_data=None):
        """
        Train the model using IRM loss
        
        Args:
            train_data: Event object with X, y, close_hist_mine
            val_data: Optional Event object for validation (not used in simple version)
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
            test_data: Event object with X (y and close_hist_mine can be dummy values)
        
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


