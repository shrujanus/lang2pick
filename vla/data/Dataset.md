## Data

This folder contains dataset information used for training and evaluating the perception pipeline.

### `url.csv`

* A CSV file listing all URLs of images in the dataset.
* The dataset consists of images of **trash and recyclable materials**.
* Each row corresponds to a single image URL that can be used for downloading or referencing the dataset.

**Usage Example:**

```python
import pandas as pd

data = pd.read_csv("data/url.csv")
print(data.head())
```

**Important Note:**
*In the development container, the actual image data is stored in this folder. **Do not push raw images to GitHub** to avoid large repository sizes.*