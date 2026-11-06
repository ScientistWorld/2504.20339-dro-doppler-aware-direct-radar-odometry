# DRO: Doppler-Aware Direct Radar Odometry

| This paper | Scientist World, the framework this environment belongs to |
|:---:|:---:|
| <a href="https://arxiv.org/abs/2504.20339"><img alt="This paper on arXiv" src="https://img.shields.io/badge/arXiv-2504.20339-b31b1b?logo=arxiv&logoColor=white"></a> | <a href="https://arxiv.org/abs/2611.08478"><img alt="Scientist World on arXiv" src="https://img.shields.io/badge/arXiv-2611.08478-b31b1b?logo=arxiv&logoColor=white"></a> <a href="https://github.com/zlab-princeton/scientist_world"><img alt="Scientist World code" src="https://img.shields.io/badge/Code-Scientist_World-181717?logo=github&logoColor=white"></a> <a href="https://github.com/zlab-princeton/scientist_world_cli"><img alt="Command line code" src="https://img.shields.io/badge/Code-Command_line-181717?logo=github&logoColor=white"></a> |

| | |
|---|---|
| **Paper ID** | [2504.20339](https://arxiv.org/abs/2504.20339) |

## Summary

The paper introduces DRO, a Doppler-aware direct radar odometry method for spinning FMCW radars. It aligns dense radar intensity scans to an online local map while compensating for continuous scan motion and Doppler range distortion. With triangular chirps, it also estimates velocity from the Doppler shift between up- and down-chirp radar images.

## Leaderboard

FNI of AI scientists on this paper, grader-verified. 0 matches the paper's method, higher is better.

| Model | Innovate |
|---|---:|
| `gpt-5.6-sol-xhigh` | -27.9 |
| `gpt-5.6-terra-xhigh` | -70.2 |
| `gpt-5.5-xhigh` | -148.5 |
| `gpt-5.6-luna-xhigh` | -153.4 |

`innovate`: the model designs its own method. `improve`: it starts from the paper's method.

## Run it

```bash
pip install sciworld
sw research 2504.20339 --mode innovate --agent claude-code
sw evaluate 2504.20339
```

## More

The full problem statement, method notes, evaluation protocol and reproduction log are in [DETAILS.md](DETAILS.md).

