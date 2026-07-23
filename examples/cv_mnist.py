"""Example CV training script — pass its CONTENTS as the `script` arg to launch_training.

    launch_training(
        script=open("examples/cv_mnist.py").read(),
        run_name="mnist_cnn",
        requirements="torch torchvision",
    )

`log_metric`, `THESIS_RUN_DIR` and `SEED` are injected by the MCP at launch time.
Visualize afterwards with cv_training_curves("mnist_cnn").
"""

import os

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import datasets, transforms

torch.manual_seed(SEED)  # noqa: F821  (SEED injected)
dev = "cuda" if torch.cuda.is_available() else "cpu"

tf = transforms.ToTensor()
train = datasets.MNIST("data", train=True, download=True, transform=tf)
test = datasets.MNIST("data", train=False, download=True, transform=tf)
train_dl = torch.utils.data.DataLoader(train, batch_size=128, shuffle=True)
test_dl = torch.utils.data.DataLoader(test, batch_size=256)


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1 = nn.Conv2d(1, 16, 3, padding=1)
        self.c2 = nn.Conv2d(16, 32, 3, padding=1)
        self.fc = nn.Linear(32 * 7 * 7, 10)

    def forward(self, x):
        x = F.max_pool2d(F.relu(self.c1(x)), 2)
        x = F.max_pool2d(F.relu(self.c2(x)), 2)
        return self.fc(x.flatten(1))


net = Net().to(dev)
opt = torch.optim.Adam(net.parameters(), lr=1e-3)

for epoch in range(3):
    net.train()
    for i, (x, y) in enumerate(train_dl):
        x, y = x.to(dev), y.to(dev)
        opt.zero_grad()
        loss = F.cross_entropy(net(x), y)
        loss.backward()
        opt.step()
        if i % 100 == 0:
            log_metric(step=epoch * len(train_dl) + i, loss=float(loss))  # noqa: F821

    net.eval()
    correct = total = 0
    with torch.no_grad():
        for x, y in test_dl:
            x, y = x.to(dev), y.to(dev)
            correct += (net(x).argmax(1) == y).sum().item()
            total += len(y)
    log_metric(step=(epoch + 1) * len(train_dl), val_acc=correct / total)  # noqa: F821
    torch.save(net.state_dict(), os.path.join(THESIS_RUN_DIR, "checkpoints", f"mnist_e{epoch}.pt"))  # noqa: F821

print("training complete")
